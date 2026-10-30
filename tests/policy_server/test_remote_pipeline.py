"""Offline tests; no API calls, DNS, NGINX, root installation or live IOC."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import pwd
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "apps/policy-server/src"),
                str(ROOT / "apps/dns-agent/src"), str(ROOT / "apps/policy-sync/src")]
from policy_server.engine import compile_policy, evaluate_policy, ProposalError
from policy_server.data_adapter import adapt_data
from policy_server.__main__ import refresh
from policy_server.promote import promote, PromotionError
from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
CONFIG = {"policy_version": "v0.8-improved", "warn_threshold": 70,
          "admin_blocked_domains": ["manual-block.test"],
          "approved_malicious_domains": ["reviewed.test"],
          "official_domains": ["official.test"], "score_sources": ["lab"]}


def observed(score, *, name="question.test", source="lab", expires=60):
    return {"analysis": {"domain": name, "risk_score": score, "source": source,
                         "model_version": "lab-v1", "checked_at": NOW.isoformat(),
                         "expires_at": (NOW + timedelta(minutes=expires)).isoformat()}}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.policy = compile_policy(CONFIG)

    def test_exact_blocks_never_silently_widen(self):
        self.assertEqual(evaluate_policy("manual-block.test", config=self.policy)["action"], "BLOCK")
        sub = evaluate_policy("sub.manual-block.test", config=self.policy)
        self.assertEqual((sub["scope"], sub["action"]), ("EXACT", "UNKNOWN"))

    def test_original_v08_precedence_with_fresh_scoped_score(self):
        self.assertEqual(evaluate_policy("official.test", data=observed(82, name="official.test"),
                                         config=self.policy, now=NOW)["action"], "WARN")
        self.assertEqual(evaluate_policy("question.test", data=observed(82),
                                         config=self.policy, now=NOW)["reason_code"], "RISK_SCORE_HIGH")
        self.assertEqual(evaluate_policy("question.test", data=observed(69),
                                         config=self.policy, now=NOW)["action"], "ALLOW")

    def test_invalid_policy_and_trusted_list_conflict_rejected(self):
        for invalid in ({"warn_threshold": 70},
                        {**CONFIG, "official_domains": ["manual-block.test"]},
                        {**CONFIG, "admin_blocked_domains": [" manual-block.test "]},
                        {**CONFIG, "warn_threshold": float("nan")},
                        {**CONFIG, "score_sources": ["lab", "lab"]}):
            with self.subTest(value=invalid), self.assertRaises(ProposalError):
                compile_policy(invalid)

    def test_score_invalid_expired_untrusted_mismatch_unknown(self):
        invalid = [observed(True), observed(10**1000), observed(float('nan')),
                   observed(60, name="different.test"), observed(80, source="unknown"),
                   observed(80, expires=-1)]
        for data in invalid:
            with self.subTest(data=str(data)[:90]):
                self.assertEqual(evaluate_policy("question.test", data=data,
                                                 config=self.policy, now=NOW)["action"], "UNKNOWN")

    def test_external_admin_flags_cannot_be_promoted(self):
        raw = {"analysis": observed(82)["analysis"], "official_domains": ["question.test"]}
        self.assertEqual(set(adapt_data(raw)), {"analysis"})
        self.assertEqual(evaluate_policy("question.test", data=raw,
                                         config=self.policy, now=NOW)["action"], "UNKNOWN")
        self.assertEqual(evaluate_policy("question.test", data=adapt_data(raw),
                                         config=self.policy, now=NOW)["action"], "WARN")

    def test_domain_version_is_not_hardcoded_on_invalid_input(self):
        self.assertEqual(evaluate_policy("https://evil.test", config=self.policy)["policy_version"],
                         self.policy.version)


class RefreshTests(unittest.TestCase):
    @unittest.skipIf(os.geteuid() == 0, "dataset fetch must run as non-root")
    def test_private_dataset_and_failure_preserves_last_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "state"
            state.mkdir(mode=0o700)
            key = root / "google-key"
            key.write_text("test-only-secret\n")
            key.chmod(0o600)
            candidate = "https://malicious-example-domain.online/login"
            calls = []
            def fake(url, headers=None, limit=None):
                calls.append(url)
                if url.endswith('/feed.txt'):
                    return (candidate + "\n").encode()
                if url.startswith('https://safebrowsing.googleapis.com/v5/urls:search?'):
                    assert headers['x-goog-api-key'] == 'test-only-secret'
                    return json.dumps({"threats": [{"url": candidate,
                           "threatTypes": ["SOCIAL_ENGINEERING"]}],
                           "cacheDuration": "300s"}).encode()
                raise AssertionError("unexpected network endpoint")
            params = dict(state_dir=state, api_key_file=key, source='openphish',
                          accept_terms=True, ack_disclosure=True, ack_noncommercial=True,
                          fetch=fake, now=NOW)
            result = refresh(**params)
            latest = json.loads((state / 'latest.json').read_text())
            self.assertEqual(result['review_proposals'], 1)
            self.assertFalse(json.loads((Path(result['run_dir']) / 'review-template.json').read_text())['reviews'][0]['approved'])
            self.assertEqual(len(calls), 2)
            def fail_google(url, headers=None, limit=None):
                if url.endswith('/feed.txt'):
                    return (candidate + "\n").encode()
                raise ValueError('simulated API outage')
            with self.assertRaises(ValueError):
                refresh(**{**params, 'fetch':fail_google})
            self.assertEqual(json.loads((state / 'latest.json').read_text()), latest)
            self.assertEqual(len(list((state/'runs').iterdir())), 1)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.feed = self.root / "feed" / "edge-69"
        self.feed.mkdir(parents=True, mode=0o700)
        self.trust = self.root / "trust"
        self.trust.mkdir(mode=0o700)
        self.key = Ed25519PrivateKey.generate()
        kid = public_key_id(self.key.public_key())
        (self.trust / (kid + '.pem')).write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.release = self.root / 'release.json'

    def _policy(self, *, seq=1, domain='bad.test', empty=False):
        expires = (NOW + timedelta(minutes=10 * seq)).isoformat()
        obj = {'issued_at': (NOW + timedelta(seconds=seq-1)).isoformat(),
               'expires_at': expires,
               'rules': [] if empty else [{'domain':domain,'decision':'BLOCK','scope':'SUBTREE',
                                          'approved':True,'expires_at':expires,'evidence':'manual-lab'}]}
        encoded = canonical(sign_policy(canonical(obj), self.key, target='edge-69',
                                        sequence=seq, signed_at=NOW + timedelta(seconds=seq-1),
                                        confirm_empty=empty))
        self.release.write_bytes(encoded)
        return self.release

    def _promote(self, **kw):
        return promote(release=self.release, feed_root=self.feed.parent,
                       trusted_keys=self.trust, device='edge-69', now=NOW,
                       **kw)

    def test_dry_run_does_not_publish(self):
        self._policy()
        self.assertEqual(self._promote()['added_blocks'], ['bad.test'])
        self.assertFalse((self.feed / 'current.json').exists())

    @unittest.skipUnless(os.geteuid() == 0, 'root promotion requires isolated root fixture')
    def test_replay_and_full_snapshot_withdrawal_ack(self):
        self._policy()
        self.assertTrue(self._promote(apply=True)['published'])
        # Identical signed release retries are read-only, not a policy replay.
        repeated = self._promote(apply=True)
        self.assertTrue(repeated['already_published'])
        self.assertFalse(repeated['published'])
        self._policy(seq=2, empty=True)
        with self.assertRaises(PromotionError):
            self._promote(apply=True)
        result = self._promote(apply=True, acknowledge_withdrawals=True)
        self.assertEqual(result['withdrawn_blocks'], ['bad.test'])
        self.assertTrue((self.feed / 'current.json').exists())

    def test_invalid_signature_rejected(self):
        self._policy()
        obj = json.loads(self.release.read_text())
        obj['payload']['sequence'] = 900
        self.release.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            self._promote()


if __name__ == "__main__":
    unittest.main()
