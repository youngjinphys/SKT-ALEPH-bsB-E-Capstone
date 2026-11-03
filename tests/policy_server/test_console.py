"""Console behavior and authorization boundaries, with synthetic offline evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "apps/policy-server/src"),
                str(ROOT / "apps/dns-agent/src"),
                str(ROOT / "apps/policy-sync/src")]

from dns_agent.policy import parse_policy
from policy_server import intel
from policy_server.console import ConsoleError, ConsoleService, handler_for
from policy_server.console_assets import HTML, CSS, JS


class ConsoleTests(unittest.TestCase):
    URL = "https://malicious-example-domain.online/login"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "reviewer"
        self.workspace.mkdir(mode=0o700)
        self.token_file = self.root / "token"
        self.token_file.write_text("a" * 48)
        self.token_file.chmod(0o600)
        self.service = ConsoleService(self.workspace, self.token_file)

    def evidence(self, at=None, read_state=True):
        at = at or datetime.now(timezone.utc)
        collected = intel.collect_urls((self.URL + "\n").encode(), source="local-openphish",
                                       fetched_at=at)
        verified = intel.verify_collected(
            collected, "fake-key", checked_at=at,
            fetch=Mock(return_value=json.dumps({
                "threats": [{"url": self.URL, "threatTypes": ["SOCIAL_ENGINEERING"]}],
                "cacheDuration": "300s"
            }).encode()))
        intel.write_json(self.workspace / "verified.json", verified)
        return self.service.reviews() if read_state else None

    def approve(self, state=None):
        state = state or self.evidence()
        self.service.update_review({
            "fingerprint": state["fingerprint"], "id": state["items"][0]["id"],
            "approved": True, "acknowledge_subtree": True,
            "reviewer": "Human Reviewer",
            "reason": "Verified malicious domain and its full subdomain scope"
        })
        return state

    def test_unsigned_real_engine_output_never_publishes(self):
        state = self.approve()
        result = self.service.build({
            "fingerprint": state["fingerprint"],
            "confirm_replacement": True, "acknowledge_user_notice": True
        })
        document = self.service.download(result["draft"])
        parsed = parse_policy(document)
        self.assertEqual(parsed.rules[0].domain, "malicious-example-domain.online")
        self.assertEqual(parsed.rules[0].decision, "BLOCK")
        self.assertTrue(parsed.rules[0].approved)
        self.assertEqual(parsed.rules[0].evidence[:16], "intel-review-v2:")
        self.assertEqual(result["sha256"], parsed.digest)
        self.assertFalse(result["signed"])
        self.assertFalse(result["published"])
        self.assertEqual(self.service.deployment()["state"], "NOT_CONFIGURED")
        self.assertEqual(len(self.service.drafts()), 1)
        self.assertIn("unsigned_policy_built", [x["event"] for x in self.service.audit()])

    def test_fails_closed_when_unapproved_stale_or_undisclosed(self):
        state = self.evidence()
        request = {"fingerprint": state["fingerprint"], "confirm_replacement": True,
                   "acknowledge_user_notice": True}
        with self.assertRaises(ValueError):
            self.service.build(request)
        with self.assertRaises(ConsoleError):
            self.service.build({**request, "acknowledge_user_notice": False})
        self.approve(state)
        with self.assertRaises(ConsoleError):
            self.service.build({**request, "fingerprint": "0" * 64})
        self.evidence(datetime.now(timezone.utc) - timedelta(hours=2), read_state=False)
        # Existing reviews are intentionally bound to the old evidence; they
        # must not silently migrate to the new collection.
        with self.assertRaises(ConsoleError):
            self.service.reviews()
        self.service.reset_reviews({"confirm": "RESET_REVIEWS"})
        older = self.service.reviews()
        self.approve(older)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.service.build({"fingerprint": older["fingerprint"],
                                "confirm_replacement": True,
                                "acknowledge_user_notice": True})
        self.assertEqual(self.service.drafts(), [])

    def test_reviews_bound_to_exact_candidate_and_explicit_subtree(self):
        state = self.evidence()
        record = {"fingerprint": state["fingerprint"], "id": state["items"][0]["id"],
                  "approved": True, "acknowledge_subtree": False,
                  "reviewer": "Reviewer", "reason": "A sufficient detailed reason for approval"}
        with self.assertRaises(ConsoleError):
            self.service.update_review(record)
        with self.assertRaises(ConsoleError):
            self.service.update_review({**record, "acknowledge_subtree": True, "id": "wrong"})
        self.assertFalse(self.service.reviews()["items"][0]["approved"])

    def test_proposal_engine_is_not_a_dns_enforcement_rule(self):
        config = {"policy_version": "operator-v1", "warn_threshold": 70,
                  "admin_blocked_domains": ["blocked.example.org"],
                  "approved_malicious_domains": [], "official_domains": [],
                  "score_sources": ["lab-scanner"]}
        self.service.configure_engine(config)
        result = self.service.evaluate({"domain": "blocked.example.org"})
        self.assertEqual(result["proposal"]["action"], "BLOCK")
        self.assertEqual(result["proposal"]["scope"], "EXACT")
        self.assertIs(result["enforcing"], False)
        with self.assertRaises(ValueError):
            self.service.configure_engine({**config, "official_domains": ["blocked.example.org"]})
        self.assertEqual(self.service.engine_config()["config"], config)

    def test_fails_on_public_workspace_and_token(self):
        self.token_file.chmod(0o644)
        with self.assertRaises(ValueError):
            ConsoleService(self.workspace, self.token_file)
        self.token_file.chmod(0o600)
        self.workspace.chmod(0o755)
        with self.assertRaises(ConsoleError):
            ConsoleService(self.workspace, self.token_file)

    def test_publisher_not_confused_with_dns_apply(self):
        feed = self.root / "feed"
        (feed / "edge-69").mkdir(parents=True)
        (feed / "edge-69" / "current.json").write_text('{"fake":"unsigned"}')
        trust = self.root / "trust"
        trust.mkdir()
        service = ConsoleService(self.workspace, self.token_file,
                                 feed_root=feed, device="edge-69", trust_dir=trust)
        self.assertEqual(service.deployment()["state"], "VERIFICATION_FAILED")
        self.assertIsNone(service.deployment()["dns_applied"])

    def test_valid_signed_feed_displays_rules_but_not_dns_apply(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy

        state = self.approve()
        draft = self.service.build({
            "fingerprint": state["fingerprint"],
            "confirm_replacement": True, "acknowledge_user_notice": True
        })
        key = Ed25519PrivateKey.generate()
        key_id = public_key_id(key.public_key())
        trust = self.root / "trust"
        trust.mkdir()
        (trust / (key_id + ".pem")).write_bytes(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo))
        feed = self.root / "feed"
        (feed / "edge-69").mkdir(parents=True)
        envelope = sign_policy(self.service.download(draft["draft"]),
                               key, target="edge-69", sequence=7)
        current = feed / "edge-69" / "current.json"
        current.write_bytes(canonical(envelope))
        service = ConsoleService(self.workspace, self.token_file, feed_root=feed,
                                 device="edge-69", trust_dir=trust)
        result = service.deployment(include_rules=True)
        self.assertEqual(result["state"], "SIGNED_FILE_VERIFIED")
        self.assertEqual(result["sequence"], 7)
        self.assertEqual(result["key_id"], key_id)
        self.assertEqual(result["rules"][0]["domain"], "malicious-example-domain.online")
        self.assertEqual(result["rules"][0]["decision"], "BLOCK")
        self.assertIsNone(result["dns_applied"])
        current.write_bytes(canonical({**envelope, "signature": "a" * 86}))
        self.assertEqual(service.deployment()["state"], "VERIFICATION_FAILED")

    def test_http_auth_host_csrf_and_secure_asset_headers(self):
        handler = handler_for(self.service, "http://127.0.0.1:8765")
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        address = server.server_port

        def request(method, path, body=None, headers=None):
            conn = HTTPConnection("127.0.0.1", address, timeout=3)
            head = {"Host": "127.0.0.1:8765", **(headers or {})}
            if body is not None:
                head["Content-Type"] = "application/json"
            payload = None if body is None else json.dumps(body).encode()
            conn.putrequest(method, path, skip_host=True)
            for key, value in head.items():
                conn.putheader(key, value)
            if payload is not None:
                conn.putheader("Content-Length", str(len(payload)))
            conn.endheaders(payload)
            result = conn.getresponse()
            data = result.read()
            status = result.status
            resp_headers = dict(result.getheaders())
            conn.close()
            return status, data, resp_headers

        status, _, headers = request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(request("GET", "/api/overview")[0], 401)
        authorized = {"Authorization": "Bearer " + self.service.token}
        self.assertEqual(request("GET", "/api/overview", headers=authorized)[0], 200)
        self.assertEqual(request("GET", "/api/overview",
                                 headers={**authorized, "Host": "attacker.example"})[0], 400)
        body = {"domain": "example.org"}
        self.assertEqual(request("POST", "/api/evaluate", body, authorized)[0], 403)
        self.assertEqual(request("POST", "/api/evaluate", body,
                                 {**authorized, "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(request("POST", "/api/evaluate", body,
                                 {**authorized, "Origin": "http://127.0.0.1:8765"})[0], 422)

    def test_bundled_web_assets_require_no_network_services(self):
        self.assertIn('src="/console.js"', HTML)
        self.assertIn('id="build-form"', HTML)
        self.assertIn("no untrusted innerHTML", JS)
        self.assertIn("@media(max-width:700px)", CSS)


if __name__ == "__main__":
    unittest.main()
