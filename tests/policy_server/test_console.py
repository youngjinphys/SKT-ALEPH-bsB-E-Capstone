"""Console behavior and authorization boundaries, with synthetic offline evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from html.parser import HTMLParser
import re
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
            "revision": state["items"][0]["revision"], "approved": True, "acknowledge_subtree": True,
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
        # Recovery must work despite a now-invalid review file; reset still
        # requires the current fingerprint and exact on-disk revision.
        context = self.service.reset_context()
        self.assertTrue(context["out_of_sync"])
        self.service.reset_reviews({"confirm": "RESET_REVIEWS", **{
                                    k: context[k] for k in ("fingerprint", "review_set_revision")}})
        
        older = self.service.reviews()
        self.assertFalse(older["items"][0]["eligible"])
        with self.assertRaisesRegex(ConsoleError, "stale or protected"):
            self.approve(older)
        with self.assertRaisesRegex(ValueError, "no approved"):
            self.service.build({"fingerprint": older["fingerprint"],
                                "confirm_replacement": True,
                                "acknowledge_user_notice": True})
        self.assertEqual(self.service.drafts(), [])

    def test_reviews_bound_to_exact_candidate_and_explicit_subtree(self):
        state = self.evidence()
        record = {"fingerprint": state["fingerprint"], "id": state["items"][0]["id"],
                  "revision": state["items"][0]["revision"], "approved": True, "acknowledge_subtree": False,
                  "reviewer": "Reviewer", "reason": "A sufficient detailed reason for approval"}
        with self.assertRaises(ConsoleError):
            self.service.update_review(record)
        with self.assertRaises(ConsoleError):
            self.service.update_review({**record, "acknowledge_subtree": True, "id": "wrong"})
        self.assertFalse(self.service.reviews()["items"][0]["approved"])

    def test_review_edit_conflict_preserves_first_writer(self):
        state = self.evidence()
        old = state["items"][0]
        edit = {"fingerprint": state["fingerprint"], "id": old["id"],
                "revision": old["revision"], "approved": True,
                "acknowledge_subtree": True, "reviewer": "First Reviewer",
                "reason": "Reviewed active and exact suspicious URL evidence with host scope"}
        self.service.update_review(edit)
        from policy_server.console import ConsoleConflict
        with self.assertRaises(ConsoleConflict):
            self.service.update_review({**edit, "reviewer": "Second Reviewer"})
        latest = self.service.reviews()["items"][0]
        self.assertEqual(latest["reviewer"], "First Reviewer")
        self.assertNotEqual(latest["revision"], old["revision"])

    def test_review_order_is_independent_but_duplicates_are_rejected(self):
        now = datetime.now(timezone.utc)
        urls = [
            "https://malicious-example-domain.online/login",
            "https://another-malicious-example.biz/login"
        ]
        collected = intel.collect_urls(("\n".join(urls)+"\n").encode(),
                                       source="local-openphish", fetched_at=now)
        def remote(url, **_):
            return json.dumps({"threats": [
                {"url": x, "threatTypes": ["MALWARE"]} for x in urls
            ], "cacheDuration": "300s"}).encode()
        verified = intel.verify_collected(collected, "fake-key", checked_at=now, fetch=remote)
        intel.write_json(self.workspace / "verified.json", verified)
        state = self.service.reviews()
        self.assertEqual(len(state["items"]), 2)
        self.approve(state)
        verified["entries"].reverse()
        intel.write_json(self.workspace / "verified.json", verified)
        self.assertEqual(len(self.service.reviews()["items"]), 2)
        reviews = intel.read_json(self.workspace / "reviews.json")
        reviews["reviews"][1] = dict(reviews["reviews"][0])
        intel.write_json(self.workspace / "reviews.json", reviews)
        with self.assertRaises(ConsoleError):
            self.service.reviews()

    def test_bound_reset_does_not_erase_concurrent_review_changes(self):
        state = self.approve()
        from policy_server.console import ConsoleConflict
        old = {"confirm": "RESET_REVIEWS",
               "fingerprint": state["fingerprint"],
               "review_set_revision": self.service.reviews()["review_set_revision"]}
        current = self.service.reviews()["items"][0]
        self.service.update_review({
            "fingerprint": state["fingerprint"], "id": current["id"],
            "revision": current["revision"], "approved": False,
            "acknowledge_subtree": False, "reviewer": current["reviewer"],
            "reason": current["reason"]})
        with self.assertRaises(ConsoleConflict):
            self.service.reset_reviews(old)
        self.assertFalse(self.service.reviews()["items"][0]["approved"])

    def test_full_replacement_impact_requires_verified_baseline(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy
        state = self.approve()
        draft = self.service.build({
            "fingerprint": state["fingerprint"],
            "confirm_replacement": True, "acknowledge_user_notice": True})["draft"]
        no_base = self.service.draft_impact(draft)
        self.assertFalse(no_base["comparison_available"])
        self.assertNotIn("withdrawn_count", no_base)
        key = Ed25519PrivateKey.generate()
        fingerprint = public_key_id(key.public_key())
        trust = self.root / "trust"
        trust.mkdir()
        (trust / (fingerprint + ".pem")).write_bytes(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo))
        feed = self.root / "feed"
        (feed / "edge-69").mkdir(parents=True)
        old = intel.read_json(self.workspace / "drafts" / draft)
        old["issued_at"] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        old["rules"] = [{**old["rules"][0], "domain": "old-legacy-block.example"}]
        published = sign_policy(json.dumps(old).encode(), key, target="edge-69",
                                sequence=1)
        (feed / "edge-69" / "current.json").write_bytes(canonical(published))
        linked = ConsoleService(self.workspace, self.token_file,
                                feed_root=feed, device="edge-69", trust_dir=trust)
        impact = linked.draft_impact(draft)
        self.assertTrue(impact["comparison_available"])
        self.assertEqual(impact["withdrawn_count"], 1)
        self.assertEqual(impact["added_count"], 1)
        self.assertTrue(impact["requires_withdrawal_ack"])
        self.assertIsNone(impact["dns_applied"])

    def test_review_freshness_and_shared_hosting_are_not_misrepresented(self):
        state = self.evidence()
        self.assertEqual(state["items"][0]["eligibility_reason"], "REVIEWABLE")
        self.assertTrue(state["items"][0]["eligible"])
        now = datetime.now(timezone.utc)
        stale = self.evidence(at=now - timedelta(minutes=7))
        self.assertEqual(stale["items"][0]["eligibility_reason"], "EVIDENCE_EXPIRED")
        self.assertFalse(stale["items"][0]["fresh"])
        self.assertFalse(stale["items"][0]["eligible"])
        self.URL = "https://badaccount.github.io/login"
        protected = self.evidence()
        self.assertTrue(protected["items"][0]["fresh"])
        self.assertFalse(protected["items"][0]["eligible"])
        self.assertEqual(protected["items"][0]["eligibility_reason"],
                         "SHARED_HOSTING_BOUNDARY")
        with self.assertRaisesRegex(ConsoleError, "stale or protected"):
            self.approve(protected)
        self.assertEqual(self.service.overview()["eligible"], 0)

    def test_long_audit_log_remains_bounded_and_safe(self):
        path = self.workspace / "audit.jsonl"
        path.write_bytes((b'{"at":"2030-01-01T00:00:00Z","event":"old"}\n' * 110000))
        path.chmod(0o600)
        output = self.service.audit()
        self.assertEqual(len(output), 100)
        self.assertEqual(output[-1]["event"], "old")
        path.chmod(0o644)
        with self.assertRaises(ConsoleError):
            self.service.audit()

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

    def test_expired_feed_keeps_its_identity_and_a_bad_signature_does_not(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        end = past + timedelta(minutes=30)
        policy = {
            "issued_at": past.isoformat(), "expires_at": end.isoformat(),
            "rules": [{"domain": "google.com", "decision": "BLOCK", "scope": "SUBTREE",
                       "approved": True, "expires_at": end.isoformat(),
                       "evidence": "expired-feed-test"}]
        }
        key = Ed25519PrivateKey.generate()
        key_id = public_key_id(key.public_key())
        trust = self.root / "trust"
        trust.mkdir()
        (trust / (key_id + ".pem")).write_bytes(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo))
        feed = self.root / "feed"
        (feed / "edge-69").mkdir(parents=True)
        envelope = sign_policy(canonical(policy), key, target="edge-69", sequence=2, signed_at=past)
        current = feed / "edge-69" / "current.json"
        current.write_bytes(canonical(envelope))
        service = ConsoleService(self.workspace, self.token_file, feed_root=feed,
                                 device="edge-69", trust_dir=trust)
        result = service.deployment(include_rules=True)
        self.assertEqual(result["state"], "PUBLICATION_EXPIRED")
        self.assertEqual(result["sequence"], 2)
        self.assertEqual(result["policy_sha256"], envelope["payload"]["policy_sha256"])
        self.assertEqual(result["active_blocks"], 0)
        self.assertEqual(result["rules"][0]["domain"], "google.com")
        self.assertIsNone(result["dns_applied"])
        self.assertIn("past valid_until", result["message"])
        self.assertEqual(service.overview()["deployment"]["state"], "PUBLICATION_EXPIRED")

        current.write_bytes(canonical({**envelope, "signature": "a" * 86}))
        failed = service.deployment()
        self.assertEqual(failed["state"], "VERIFICATION_FAILED")
        self.assertNotIn("sequence", failed)
        self.assertIsNone(failed["dns_applied"])

        future = datetime.now(timezone.utc) + timedelta(hours=2)
        later = future + timedelta(minutes=10)
        ahead = {
            "issued_at": future.isoformat(), "expires_at": later.isoformat(),
            "rules": [{"domain": "example.org", "decision": "BLOCK", "scope": "SUBTREE",
                       "approved": True, "expires_at": later.isoformat(),
                       "evidence": "future-feed-test"}]
        }
        current.write_bytes(canonical(sign_policy(
            canonical(ahead), key, target="edge-69", sequence=3, signed_at=future)))
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
        status, selected, _ = request("GET", "/api/deployment/edge-70", headers=authorized)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(selected)["device"], "edge-70")
        self.assertEqual(json.loads(selected)["state"], "NOT_CONFIGURED")
        self.assertEqual(request("GET", "/api/deployment/edge-70/extra", headers=authorized)[0], 404)
        self.assertEqual(request("GET", "/api/deployment/../secret", headers=authorized)[0], 404)
        self.assertEqual(request("GET", "/api/overview",
                                 headers={**authorized, "Host": "attacker.example"})[0], 400)
        body = {"domain": "example.org"}
        self.assertEqual(request("POST", "/api/evaluate", body, authorized)[0], 403)
        self.assertEqual(request("POST", "/api/evaluate", body,
                                 {**authorized, "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(request("POST", "/api/evaluate", body,
                                 {**authorized, "Origin": "http://127.0.0.1:8765"})[0], 422)
        self.assertEqual(request("GET", "/api/drafts/invalid/impact", headers=authorized)[0], 422)

    def test_bundled_web_assets_require_no_network_services(self):
        self.assertIn('src="/console.js"', HTML)
        self.assertIn('id="build-form"', HTML)
        self.assertIn('id="intel-refresh-form"', HTML)
        self.assertIn('id="intel-import"', HTML)
        self.assertIn("/api/intel/refresh", JS)
        self.assertIn("IMPORT_VERIFIED", JS)
        self.assertIn('id="verification-status"', HTML)
        self.assertIn('id="review-eligibility"', HTML)
        self.assertIn("no untrusted innerHTML", JS)
        self.assertIn("SESSION_IDLE_MS", JS)
        self.assertIn("currentRequest", JS)
        self.assertIn("sessionEpoch++", JS)
        self.assertIn('if(!$("authorized").hidden) lock()', JS)
        self.assertIn('id="draft-impact"', HTML)
        self.assertIn("@media(max-width:700px)", CSS)
        self.assertIn("prefers-reduced-transparency", CSS)
        self.assertIn("forced-colors", CSS)
        self.assertIn("SKT-ALEPH-PR-Page", CSS)

    def test_operator_visual_hierarchy_navigation_and_responsive_contract(self):
        # Visual surfaces reflect real data already exposed by their APIs.
        # Navigation buttons must remain keyboard accessible and no offline
        # dashboard element should fabricate a healthy DNS apply status.
        for target in ("reviews", "drafts", "deployment"):
            self.assertIn('data-go="'+target+'"', HTML)
        self.assertIn('id="page-title" tabindex="-1"', HTML)
        self.assertIn('class="section-heading section-heading--metrics"', HTML)
        self.assertIn('class="strip-indicator"', HTML)
        self.assertIn('class="intel-activity-line"', HTML)
        self.assertIn('data-metric="pending"', HTML)
        self.assertIn('function navigateTo(name)', JS)
        self.assertIn('article.dataset.tone=kind;', JS)
        self.assertIn('refreshPanel.dataset.status=status.state', JS)
        self.assertIn('aria-label="4단계 서명된 게시 정책 확인"', HTML)
        self.assertIn('DNS 적용은 별도 확인', HTML)
        for fragment in ('@media (max-width: 700px)', '@media (max-width: 400px)',
                         '@media (prefers-reduced-motion: reduce)',
                         '@media (prefers-reduced-transparency: reduce)',
                         '@media (forced-colors: active)', '.nav-item:focus-visible',
                         '.intel-refresh-panel[data-status="RUNNING"]',
                         '.node-card[data-tone="bad"]'):
            if fragment == '.nav-item:focus-visible':
                self.assertIn('button:focus-visible', CSS)
            else:
                self.assertIn(fragment, CSS)
        self.assertNotIn('<script src="https://', HTML)

    def test_header_controls_share_alignment_and_status_wraps_as_one_item(self):
        # Static contracts only. Real geometry is checked by dashboard_header.py.
        self.assertIn('.topbar-actions>.quiet-button{display:inline-flex;align-items:center;justify-content:center;', CSS)
        self.assertIn('white-space:nowrap;text-decoration:none', CSS)
        self.assertIn('.topbar-actions>.icon-button{flex:0 0 44px;width:44px;height:44px}', CSS)
        self.assertIn('@media(min-width:701px) and (max-width:1100px)', CSS)
        self.assertIn('.topbar-context{flex:1 0 100%}', CSS)
        self.assertIn('.connection-status>.connection-dot{flex:0 0 8px}', CSS)
        self.assertIn('max-width:min(100%,20rem)', CSS)
        self.assertIn('overflow:hidden;clip-path:inset(50%);white-space:nowrap', CSS)
        self.assertIn('overflow-wrap:anywhere', CSS)
        self.assertIn('[hidden]{display:none!important}', CSS)
        self.assertIn('<span class="connection-status" role="status"><span class="connection-dot" id="connection-dot" aria-hidden="true"></span><span class="connection" id="connection-text">콘솔 인증 필요</span></span>', HTML)
        self.assertIn('id="logout-button" hidden', HTML)

    def test_dashboard_ids_and_accessible_markup_are_consistent(self):
        class DOM(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if "id" in attrs:
                    self.ids.append(attrs["id"])
        dom = DOM()
        dom.feed(HTML)
        self.assertEqual(len(dom.ids), len(set(dom.ids)), "duplicate HTML ids")
        self.assertIn('href="#main-content"', HTML)
        self.assertIn('aria-hidden="true"', HTML)
        for required in re.findall(r'\$\("([a-z][a-z0-9-]+)"\)', JS):
            self.assertIn(required, dom.ids, "JS references missing HTML element: "+required)

    def test_overview_degrades_without_hiding_independent_status(self):
        state=self.evidence()
        self.assertFalse(self.service.overview()["evidence_error"])
        evidence=self.workspace/"verified.json"
        evidence.chmod(0o644)
        damaged=self.service.overview()
        self.assertTrue(damaged["evidence_error"])
        self.assertIsNone(damaged["candidates"])
        self.assertEqual(damaged["nodes"]["registered"],0)
        self.assertEqual(damaged["drafts"],0)
        evidence.chmod(0o600)

        from policy_server import intel as intel_module
        intel_module.write_json(self.workspace/"nodes.json",{"broken":True})
        damaged=self.service.overview()
        self.assertTrue(damaged["nodes_error"])
        self.assertIsNone(damaged["nodes"]["registered"])
        self.assertEqual(damaged["candidates"],1)

        (self.workspace/"drafts"/"policy-20261103T000000Z-012345abcdef.json").write_bytes(
            b'not-json')
        damaged=self.service.overview()
        self.assertTrue(damaged["drafts_error"])
        self.assertIsNone(damaged["drafts"])
        self.assertFalse(damaged["evidence_error"])

    def test_overview_never_confuses_review_and_dns_enforcement(self):
        overview = self.service.overview()
        self.assertTrue(overview["evidence_missing"])
        self.assertEqual(overview["eligible"], 0)
        self.assertEqual(overview["approved_eligible"], 0)
        self.assertIsNone(overview["next_expiry"])
        self.assertIsNone(overview["deployment"]["dns_applied"])
        state=self.evidence()
        overview=self.service.overview()
        self.assertFalse(overview["evidence_missing"])
        self.assertEqual(overview["eligible"], 1)
        self.assertEqual(overview["fresh"], 1)
        self.assertEqual(overview["approved_eligible"], 0)
        self.approve(state)
        self.assertEqual(self.service.overview()["approved_eligible"], 1)


if __name__ == "__main__":
    unittest.main()
