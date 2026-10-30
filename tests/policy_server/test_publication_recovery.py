"""Isolated publisher failures: no HTTP, DNS or real server paths are used."""
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'apps/policy-server/src'), str(ROOT / 'apps/policy-sync/src'),
                str(ROOT / 'apps/dns-agent/src')]
m = importlib.import_module('policy_server.promote')
from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / 'feed' / 'edge-69'
        self.folder.mkdir(parents=True, mode=0o700)
        self.trust = self.root / 'trust'
        self.trust.mkdir(mode=0o700)
        self.key = self.new_key()
        self.release = self.root / 'release.json'

    def new_key(self):
        key = Ed25519PrivateKey.generate()
        (self.trust / (public_key_id(key.public_key()) + '.pem')).write_bytes(
            key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo))
        return key

    def candidate(self, seq=1, *, minutes=10, key=None):
        until = (NOW + timedelta(minutes=minutes)).isoformat()
        policy = {'issued_at': (NOW + timedelta(seconds=seq-1)).isoformat(),
                  'expires_at': until, 'rules': [{'domain': 'bad.test', 'decision': 'BLOCK',
                   'scope': 'SUBTREE', 'approved': True, 'expires_at': until,
                   'evidence': 'controlled-regression-only'}]}
        envelope = sign_policy(canonical(policy), key or self.key, target='edge-69',
                               sequence=seq, signed_at=NOW + timedelta(seconds=seq-1))
        self.release.write_bytes(canonical(envelope))
        return envelope

    def run_publish(self, **kwargs):
        return m.promote(release=self.release, feed_root=self.folder.parent,
                         trusted_keys=self.trust, device='edge-69', now=NOW, **kwargs)

    def test_symlinked_feed_parent_is_rejected(self):
        self.candidate()
        linked = self.root / 'linked'
        linked.symlink_to(self.folder.parent, target_is_directory=True)
        with self.assertRaises(m.PromotionError):
            m.promote(release=self.release, feed_root=linked, trusted_keys=self.trust,
                      device='edge-69', now=NOW)
        self.assertFalse((self.folder / 'current.json').exists())

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_retry_after_public_file_write_recovers_watermark(self):
        self.candidate()
        actual_write = m._write
        def fail_receipt(path, data, mode=0o644):
            if path.name == '.publication.json':
                raise OSError('injected receipt storage failure')
            return actual_write(path, data, mode)
        with patch.object(m, '_write', side_effect=fail_receipt), self.assertRaises(OSError):
            self.run_publish(apply=True)
        self.assertTrue((self.folder / 'current.json').is_file())
        result = self.run_publish(apply=True)
        self.assertTrue(result['recovered'])
        self.assertEqual(json.loads((self.folder / '.publication.json').read_text())['sequence'], 1)
        self.assertFalse((self.folder / '.pending-publication.json').exists())

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_completed_identical_retry_is_read_only(self):
        self.candidate()
        self.run_publish(apply=True)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.iterdir()}
        result = self.run_publish(apply=True)
        self.assertTrue(result['already_published'])
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.folder.iterdir()}
        self.assertEqual(before, after)

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_revoked_old_signer_does_not_prevent_explicit_rotation(self):
        self.candidate()
        self.run_publish(apply=True)
        old_id = public_key_id(self.key.public_key())
        other = self.new_key()
        (self.trust / (old_id + '.pem')).unlink()
        self.candidate(2, key=other)
        with self.assertRaises(m.PromotionError):
            self.run_publish(apply=True)
        result = self.run_publish(apply=True, acknowledge_key_rotation=True)
        self.assertTrue(result['published'])
        self.assertEqual(json.loads((self.folder / 'current.json').read_text())['key_id'],
                         public_key_id(other.public_key()))

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_missing_current_with_existing_receipt_is_not_silent_bootstrap(self):
        self.candidate()
        self.run_publish(apply=True)
        (self.folder / 'current.json').unlink()
        self.candidate(2)
        with self.assertRaises(m.PromotionError):
            self.run_publish(apply=True)
        self.assertFalse((self.folder / 'current.json').exists())

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_shorter_block_lifetime_needs_withdrawal_ack(self):
        self.candidate(minutes=10)
        self.run_publish(apply=True)
        self.candidate(2, minutes=3)
        with self.assertRaises(m.PromotionError):
            self.run_publish(apply=True)
        result = self.run_publish(apply=True, acknowledge_withdrawals=True)
        self.assertEqual(result['shortened_blocks'], ['bad.test'])

    def test_malformed_journal_is_not_ignored(self):
        self.candidate()
        journal = self.folder / '.pending-publication.json'
        journal.write_text('{"format":1,"format":2}')
        journal.chmod(0o600)
        with self.assertRaises(ValueError):
            self.run_publish()

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_retry_after_prepared_intent_but_before_public_write(self):
        self.candidate()
        actual_write = m._write
        def fail_current(path, data, mode=0o644):
            if path.name == 'current.json':
                raise OSError('injected public file failure')
            return actual_write(path, data, mode)
        with patch.object(m, '_write', side_effect=fail_current), self.assertRaises(OSError):
            self.run_publish(apply=True)
        self.assertTrue((self.folder / '.pending-publication.json').exists())
        self.assertFalse((self.folder / 'current.json').exists())
        self.assertTrue(self.run_publish(apply=True)['recovered'])

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_expired_unserved_intent_aborts_without_changing_old_policy(self):
        self.candidate()
        self.run_publish(apply=True)
        old_current = (self.folder / 'current.json').read_bytes()
        old_receipt = (self.folder / '.publication.json').read_bytes()
        self.candidate(2, minutes=3)
        actual_write = m._write
        def fail_current(path, data, mode=0o644):
            if path.name == 'current.json':
                raise OSError('injected public file failure')
            return actual_write(path, data, mode)
        with patch.object(m, '_write', side_effect=fail_current), self.assertRaises(OSError):
            self.run_publish(apply=True, acknowledge_withdrawals=True)
        with self.assertRaisesRegex(m.PromotionError, 'expired before publication'):
            m.promote(release=self.release, feed_root=self.folder.parent, trusted_keys=self.trust,
                      device='edge-69', now=NOW+timedelta(minutes=5), apply=True)
        self.assertEqual((self.folder / 'current.json').read_bytes(), old_current)
        self.assertEqual((self.folder / '.publication.json').read_bytes(), old_receipt)
        self.assertFalse((self.folder / '.pending-publication.json').exists())

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_expired_already_served_release_repairs_receipt_without_extending_ttl(self):
        self.candidate()
        actual_write = m._write
        def fail_receipt(path, data, mode=0o644):
            if path.name == '.publication.json':
                raise OSError('injected receipt failure')
            return actual_write(path, data, mode)
        with patch.object(m, '_write', side_effect=fail_receipt), self.assertRaises(OSError):
            self.run_publish(apply=True)
        before = (self.folder / 'current.json').read_bytes()
        result = m.promote(release=self.release, feed_root=self.folder.parent,
                           trusted_keys=self.trust, device='edge-69',
                           now=NOW+timedelta(minutes=11), apply=True)
        self.assertTrue(result['recovered'])
        self.assertTrue(result['expired'])
        self.assertFalse(result['published'])
        self.assertEqual((self.folder / 'current.json').read_bytes(), before)

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_pending_release_cannot_be_replaced_by_another_signed_candidate(self):
        self.candidate()
        original = self.release.read_bytes()
        actual_write = m._write
        def fail_receipt(path, data, mode=0o644):
            if path.name == '.publication.json':
                raise OSError('injected receipt failure')
            return actual_write(path, data, mode)
        with patch.object(m, '_write', side_effect=fail_receipt), self.assertRaises(OSError):
            self.run_publish(apply=True)
        self.candidate(2)
        with self.assertRaisesRegex(m.PromotionError, 'original signed release'):
            self.run_publish(apply=True)
        self.release.write_bytes(original)
        self.assertTrue(self.run_publish(apply=True)['recovered'])

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_legacy_receipt_migrates_only_with_valid_old_signature(self):
        self.candidate()
        self.run_publish(apply=True)
        target = self.folder / '.publication.json'
        state = json.loads(target.read_text())
        target.write_bytes(canonical({k: state[k] for k in ('sequence', 'payload_sha256')}))
        self.candidate(2)
        self.assertTrue(self.run_publish(apply=True)['published'])
        self.assertEqual(json.loads(target.read_text())['format'], 2)

    @unittest.skipUnless(os.geteuid() == 0, 'root-only publication in temporary fixtures')
    def test_dry_run_of_pending_recovery_never_mutates_files(self):
        self.candidate()
        actual_write = m._write
        def fail_receipt(path, data, mode=0o644):
            if path.name == '.publication.json':
                raise OSError('injected receipt failure')
            return actual_write(path, data, mode)
        with patch.object(m, '_write', side_effect=fail_receipt), self.assertRaises(OSError):
            self.run_publish(apply=True)
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.assertTrue(self.run_publish()['recovery_pending'])
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)
