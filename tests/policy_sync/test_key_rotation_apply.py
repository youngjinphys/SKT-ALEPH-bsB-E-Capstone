"""Real signatures/files; root replay/intent checks, no live DNS publication."""
from datetime import timedelta
import json
import os
from pathlib import Path
import pwd
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aleph_policy_sync import sync
from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy
from test_snapshot import NOW, policy, trust


@unittest.skipUnless(os.geteuid() == 0, 'Root apply test uses a private temporary fixture')
class KeyRotationApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.user = pwd.getpwnam('nobody')
        self.inbox = self.root/'inbox'
        self.inbox.mkdir(mode=0o700)
        os.chown(self.inbox, self.user.pw_uid, self.user.pw_gid)
        self.state = self.root/'state'
        self.state.mkdir(mode=0o700)
        self.trust = self.root/'trust'
        self.trust.mkdir(mode=0o700)
        self.key = Ed25519PrivateKey.generate()
        trust(self.trust, self.key)
        self.published = []
        self.live = None

    def stage(self, sequence, at, key=None):
        envelope = sign_policy(canonical(policy(at)), key or self.key,
                               target='edge-69', sequence=sequence, signed_at=at)
        target = self.inbox/'current.json'
        target.write_bytes(canonical(envelope))
        target.chmod(0o600)
        os.chown(target, self.user.pw_uid, self.user.pw_gid)

    def apply(self, at):
        def publish(candidate):
            data = candidate.read_bytes()
            self.published.append(data)
            parsed = sync.verify_envelope(
                (self.inbox/'current.json').read_bytes(), expected_device='edge-69',
                trust_dir=self.trust, now=at)[1]
            self.live = parsed

        def attest(digest):
            if self.live is None or self.live.digest != digest or self.live.expires_at <= at:
                raise sync.SyncError('live DNS cannot attest an expired or different policy')

        return sync.apply_once(device='edge-69', trust_dir=self.trust,
                               inbox_dir=self.inbox, fetch_user=self.user.pw_name,
                               state_dir=self.state, dns_admin=Path('/unused-test-admin'),
                               now=at, publisher=publish, attestor=attest)

    def rotate(self):
        (self.trust/(public_key_id(self.key.public_key())+'.pem')).unlink()
        self.key = Ed25519PrivateKey.generate()
        trust(self.trust, self.key)

    def test_retired_key_does_not_reset_root_replay_watermark(self):
        self.stage(5, NOW)
        self.assertEqual(self.apply(NOW), 'applied')
        saved = (self.state/'applied.json').read_bytes()
        self.rotate()
        later = NOW+timedelta(minutes=1)
        self.stage(4, later)
        with self.assertRaisesRegex(sync.SyncError, 'rollback'):
            self.apply(later)
        self.assertEqual((self.state/'applied.json').read_bytes(), saved)
        self.assertEqual(len(self.published), 1)

    def test_trusted_successor_with_later_sequence_can_apply(self):
        self.stage(5, NOW)
        self.apply(NOW)
        self.rotate()
        later = NOW+timedelta(minutes=1)
        self.stage(6, later)
        self.assertEqual(self.apply(later), 'applied')
        self.assertEqual(json.loads((self.state/'applied.json').read_text())['sequence'], 6)
        self.assertEqual(len(self.published), 2)

    def test_untrusted_successor_never_updates_root_state(self):
        self.stage(5, NOW)
        self.apply(NOW)
        saved = (self.state/'applied.json').read_bytes()
        self.rotate()
        later = NOW+timedelta(minutes=1)
        self.stage(6, later, key=Ed25519PrivateKey.generate())
        with self.assertRaises(FileNotFoundError):
            self.apply(later)
        self.assertEqual((self.state/'applied.json').read_bytes(), saved)
        self.assertEqual(len(self.published), 1)

    def test_expired_uncommitted_apply_preserves_journal_for_manual_recovery(self):
        # This is a documented fail-closed boundary, NOT an automatic recovery fix.
        self.stage(5, NOW)
        actual_write = sync.atomic_private
        def failed_receipt(path, data, *, owner):
            if path.name == 'applied.json':
                raise OSError('simulated disk error after DNS publication')
            return actual_write(path, data, owner=owner)
        with patch.object(sync, 'atomic_private', side_effect=failed_receipt):
            with self.assertRaises(OSError):
                self.apply(NOW)
        saved = (self.state/'pending-apply.json').read_bytes()
        later = NOW+timedelta(minutes=13)
        self.stage(6, later)
        with self.assertRaisesRegex(sync.SyncError, 'no verified fallback'):
            self.apply(later)
        self.assertEqual((self.state/'pending-apply.json').read_bytes(), saved)
        self.assertFalse((self.state/'applied.json').exists())
        self.assertEqual(len(self.published), 1)


if __name__ == '__main__':
    unittest.main()
