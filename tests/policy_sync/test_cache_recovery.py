"""Non-root cache recovery with real Ed25519 verification; HTTP transport is fake."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from aleph_policy_sync import sync
from aleph_policy_sync.snapshot import SnapshotError, canonical, public_key_id, sign_policy

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


@unittest.skipIf(os.geteuid() == 0, 'fetcher must be tested as an unprivileged user')
class CacheRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inbox = self.root/'inbox'
        self.inbox.mkdir(mode=0o700)
        self.trust = self.root/'trust'
        self.trust.mkdir(mode=0o700)
        self.key = Ed25519PrivateKey.generate()
        self.trust_key(self.key)
        self.requests = []

    def trust_key(self, key):
        path = self.trust/(public_key_id(key.public_key())+'.pem')
        path.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        path.chmod(0o644)
        return path

    def signed(self, sequence=3, *, domain='blocked.example'):
        expires = (NOW+timedelta(minutes=15)).isoformat()
        data = {'issued_at': NOW.isoformat(), 'expires_at': expires, 'rules': [
            {'domain': domain, 'decision': 'BLOCK', 'scope': 'SUBTREE',
             'approved': True, 'expires_at': expires, 'evidence': 'synthetic review'}]}
        return canonical(sign_policy(canonical(data), self.key, target='edge-69',
                                     sequence=sequence, signed_at=NOW))+b'\n'

    def fetch(self, body):
        requests = self.requests
        class Transport:
            def open(self, request, **_):
                requests.append(request)
                return self
            def __enter__(self): return self
            def __exit__(self, *_): pass
            status = 200
            headers = {'ETag': '"signed-fixture"'}
            def read(self, limit): return body[:limit]
        with patch.object(sync, 'build_opener', return_value=Transport()):
            return sync.fetch_once(url='https://policy.example/edge-69/current.json',
                                   device='edge-69', trust_dir=self.trust,
                                   inbox_dir=self.inbox, now=NOW)

    def corrupt_meta(self, value):
        path = self.inbox/'fetch-state.json'
        if value is None:
            path.unlink()
        else:
            path.write_bytes(value)
            path.chmod(0o600)

    def test_bounded_malformed_metadata_does_not_block_verified_successor(self):
        for value in (b'{', b'null', b'[]', b'{"etag":1}',
                      b'{"etag":"x","etag":"y"}', b'\xff'):
            with self.subTest(value=value):
                (self.inbox/'current.json').unlink(missing_ok=True)
                (self.inbox/'fetch-state.json').unlink(missing_ok=True)
                self.fetch(self.signed())
                self.corrupt_meta(value)
                try:
                    outcome = self.fetch(self.signed(4))
                except (SnapshotError, sync.SyncError) as exc:
                    self.fail(f'disposable metadata blocked a trusted fresh response: {exc}')
                self.assertEqual(outcome, 'downloaded')
                self.assertIsNone(self.requests[-1].get_header('If-none-match'))
                self.assertEqual((self.inbox/'current.json').read_bytes(), self.signed(4))
                # Next subcase starts with an independent, valid sequence.
                (self.inbox/'current.json').unlink()
                (self.inbox/'fetch-state.json').unlink()

    def test_missing_or_mismatched_metadata_never_discards_signed_sequence(self):
        for mismatch in (None, b'{"etag":"old","envelope_sha256":"'+b'0'*64+b'"}'):
            with self.subTest(metadata=mismatch):
                self.fetch(self.signed(3))
                original = (self.inbox/'current.json').read_bytes()
                self.corrupt_meta(mismatch)
                with self.assertRaisesRegex(sync.SyncError, 'rollback'):
                    self.fetch(self.signed(2))
                self.assertEqual((self.inbox/'current.json').read_bytes(), original)
                (self.inbox/'current.json').unlink()
                (self.inbox/'fetch-state.json').unlink(missing_ok=True)

    def test_missing_metadata_still_rejects_same_sequence_conflict(self):
        self.fetch(self.signed())
        self.corrupt_meta(None)
        before = (self.inbox/'current.json').read_bytes()
        with self.assertRaisesRegex(sync.SyncError, 'conflicting'):
            self.fetch(self.signed(domain='different.example'))
        self.assertEqual((self.inbox/'current.json').read_bytes(), before)

    def test_corrupt_metadata_never_authorizes_an_invalid_new_signature(self):
        self.fetch(self.signed())
        before = (self.inbox/'current.json').read_bytes()
        self.corrupt_meta(b'{')
        n = len(self.requests)
        with self.assertRaises(SnapshotError):
            self.fetch(self.signed(4).replace(b'"sequence":4', b'"sequence":5'))
        self.assertEqual(len(self.requests), n+1, 'new signature must actually be checked')
        self.assertEqual((self.inbox/'current.json').read_bytes(), before)
        self.assertEqual((self.inbox/'fetch-state.json').read_bytes(), b'{')

    def test_unsafe_metadata_is_not_silently_repaired(self):
        self.fetch(self.signed())
        meta = self.inbox/'fetch-state.json'
        meta.chmod(0o666)
        n = len(self.requests)
        with self.assertRaises(SnapshotError): self.fetch(self.signed(4))
        self.assertEqual(len(self.requests), n)
        meta.unlink()
        target = self.root/'external'
        target.write_text('preserve')
        meta.symlink_to(target)
        with self.assertRaises(OSError): self.fetch(self.signed(4))
        self.assertEqual(target.read_text(), 'preserve')
        self.assertEqual(len(self.requests), n)

    def test_unsigned_or_retired_cache_cannot_block_new_trusted_key(self):
        self.fetch(self.signed())
        old = self.trust/(public_key_id(self.key.public_key())+'.pem')
        old.unlink()
        self.key = Ed25519PrivateKey.generate()
        self.trust_key(self.key)
        self.assertEqual(self.fetch(self.signed(4)), 'downloaded')
        self.assertIsNone(self.requests[-1].get_header('If-none-match'))

    def test_replay_watermark_reader_still_rejects_corrupt_root_state(self):
        # HTTP metadata recovery must not weaken read_state used by root apply.
        state = self.root/'applied.json'
        state.write_bytes(b'{')
        state.chmod(0o600)
        with self.assertRaises(SnapshotError):
            sync.read_state(state, owner=os.geteuid())


if __name__ == '__main__': unittest.main()
