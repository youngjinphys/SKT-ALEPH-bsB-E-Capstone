"""Root publication crash recovery; real files and signatures, no live services."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from aleph_policy_sync.snapshot import SnapshotError, canonical, public_key_id, sign_policy
from policy_server import promote as p

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


@unittest.skipUnless(os.geteuid() == 0, 'publication apply requires root-owned fixtures')
class CommittedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.feed = self.root/'feed'
        self.feed.mkdir(mode=0o755)
        self.folder = self.feed/'edge-69'
        self.folder.mkdir(mode=0o755)
        self.trust = self.root/'trust'
        self.trust.mkdir(mode=0o700)
        self.key = Ed25519PrivateKey.generate()
        self.keyfile = self.add_key(self.key)
        self.release = self.make_release(self.key, 1, NOW)
        self.pending = self.folder/'.pending-publication.json'

    def add_key(self, key):
        target = self.trust/(public_key_id(key.public_key())+'.pem')
        target.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        target.chmod(0o644)
        return target

    def make_release(self, key, sequence, now):
        expires = (now+timedelta(minutes=10)).isoformat()
        data = {'issued_at': now.isoformat(), 'expires_at': expires, 'rules': [
            {'domain':'blocked.example', 'scope':'SUBTREE', 'decision':'BLOCK',
             'approved':True, 'expires_at':expires, 'evidence':'synthetic-review'}]}
        env = sign_policy(canonical(data), key, target='edge-69', sequence=sequence,
                          signed_at=now)
        target = self.root/f'release-{sequence}.json'
        target.write_bytes(canonical(env)+b'\n')
        return target

    def call(self, *, release=None, now=NOW, apply=True, **kw):
        return p.promote(release=release or self.release, feed_root=self.feed,
                         trusted_keys=self.trust, device='edge-69', now=now,
                         apply=apply, **kw)

    def commit_then_interrupt_cleanup(self):
        original = Path.unlink
        pending = self.pending
        def fail(path, *a, **kw):
            if path == pending: raise OSError('injected journal cleanup failure')
            return original(path, *a, **kw)
        with patch.object(Path, 'unlink', fail):
            with self.assertRaisesRegex(OSError, 'cleanup failure'): self.call()
        self.assertTrue(self.pending.exists())
        self.assertTrue((self.folder/'.publication.json').exists())

    def test_committed_receipt_can_finish_cleanup_after_key_revocation(self):
        self.commit_then_interrupt_cleanup()
        current = (self.folder/'current.json').read_bytes()
        receipt = (self.folder/'.publication.json').read_bytes()
        self.keyfile.unlink()
        with patch.object(p, '_write') as writes:
            try:
                result = self.call()
            except FileNotFoundError as exc:
                self.fail(f'committed receipt cleanup depends on revoked key: {exc}')
            writes.assert_not_called()
        self.assertTrue(result['recovered'])
        self.assertFalse(result['published'], 'cleanup must not claim a new publication')
        self.assertFalse(self.pending.exists())
        self.assertEqual((self.folder/'current.json').read_bytes(), current)
        self.assertEqual((self.folder/'.publication.json').read_bytes(), receipt)
        # A different new key is still independently verified and acknowledged.
        key = Ed25519PrivateKey.generate()
        self.add_key(key)
        next_release = self.make_release(key, 2, NOW+timedelta(seconds=1))
        with self.assertRaisesRegex(p.PromotionError, 'rotation'):
            self.call(release=next_release, now=NOW+timedelta(seconds=1))
        self.assertTrue(self.call(release=next_release, now=NOW+timedelta(seconds=1),
                                  acknowledge_key_rotation=True)['published'])

    def test_expired_committed_cleanup_preserves_original_expiry(self):
        self.commit_then_interrupt_cleanup()
        before = (self.folder/'current.json').read_bytes()
        self.keyfile.unlink()
        try:
            result = self.call(now=NOW+timedelta(minutes=11))
        except FileNotFoundError as exc:
            self.fail(f'expired committed cleanup must not re-trust revoked key: {exc}')
        self.assertTrue(result['expired'])
        self.assertEqual(result['active_blocks'], 0)
        self.assertFalse(result['published'])
        self.assertEqual((self.folder/'current.json').read_bytes(), before)

    def test_uncommitted_receipt_still_requires_currently_trusted_signer(self):
        write = p._write
        def fail(path, *args, **kwargs):
            if path.name == '.publication.json': raise OSError('receipt not committed')
            return write(path, *args, **kwargs)
        with patch.object(p, '_write', fail):
            with self.assertRaises(OSError): self.call()
        before = (self.folder/'current.json').read_bytes()
        self.keyfile.unlink()
        with self.assertRaises((SnapshotError, FileNotFoundError)): self.call()
        self.assertTrue(self.pending.exists())
        self.assertFalse((self.folder/'.publication.json').exists())
        self.assertEqual((self.folder/'current.json').read_bytes(), before)

    def test_tampered_current_is_not_covered_by_committed_receipt(self):
        self.commit_then_interrupt_cleanup()
        current = self.folder/'current.json'
        current.write_bytes(current.read_bytes().replace(b'blocked.example', b'changed.example'))
        with self.assertRaises(p.PromotionError): self.call()
        self.assertTrue(self.pending.exists())

    def test_legacy_receipt_does_not_authorize_revoked_key_cleanup(self):
        self.commit_then_interrupt_cleanup()
        path = self.folder/'.publication.json'
        value = json.loads(path.read_bytes())
        path.write_bytes(canonical({k:value[k] for k in ('sequence','payload_sha256')}))
        path.chmod(0o600)
        self.keyfile.unlink()
        with self.assertRaises((p.PromotionError, SnapshotError, FileNotFoundError)): self.call()
        self.assertTrue(self.pending.exists())

    def test_preview_does_not_change_committed_pending_files(self):
        self.commit_then_interrupt_cleanup()
        self.keyfile.unlink()
        before = {f.name:f.read_bytes() for f in self.folder.iterdir()}
        try:
            result = self.call(apply=False)
        except FileNotFoundError as exc:
            self.fail(f'nonmutating committed preview requires revoked key: {exc}')
        self.assertFalse(result['published'])
        self.assertTrue(result['recovery_pending'])
        self.assertEqual({f.name:f.read_bytes() for f in self.folder.iterdir()}, before)


if __name__ == '__main__': unittest.main()
