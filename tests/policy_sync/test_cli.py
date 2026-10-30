"""Offline CLI release signing and verification. No DNS privileges/network."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from aleph_policy_sync.snapshot import public_key_id, canonical
from aleph_policy_sync.sync import file_lock, SyncError
from test_snapshot import NOW, policy


class CliTests(unittest.TestCase):
    def test_transaction_lock_rejects_overlapping_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            with file_lock(path,owner=os.geteuid()):
                with self.assertRaisesRegex(SyncError,'another policy'):
                    with file_lock(path,owner=os.geteuid()):pass

    @unittest.skipIf(os.geteuid()==0,'Private signing keys must be operated without root')
    def test_cli_sign_key_id_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            key=Ed25519PrivateKey.generate()
            secret=root/'signing.pem'
            secret.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            secret.chmod(0o600)
            public=root/'public.pem'
            public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                              serialization.PublicFormat.SubjectPublicKeyInfo))
            public.chmod(0o644)
            kid=public_key_id(key.public_key())
            trust=root/'trusted';trust.mkdir(mode=0o700)
            (trust/(kid+'.pem')).write_bytes(public.read_bytes())
            (trust/(kid+'.pem')).chmod(0o644)
            raw=root/'approved.json';raw.write_bytes(canonical(policy(NOW)));raw.chmod(0o600)
            release=root/'release.json'
            env=dict(os.environ)
            # The module must never depend on shell environment secrets.
            sign=subprocess.run([sys.executable,'-m','aleph_policy_sync','sign',
                                 '--policy',str(raw),'--private-key',str(secret),
                                 '--device-id','edge-69','--sequence','1',
                                 '--output',str(release),'--confirm-replacement'],
                                env=env,capture_output=True,text=True)
            # A fixed 2030 fixture cannot be signed at the current wall clock.
            # Exercise the production CLI against current real time instead.
            self.assertNotEqual(sign.returncode,0)
            from datetime import datetime,timezone,timedelta
            now=datetime.now(timezone.utc)
            raw.write_bytes(canonical(policy(now)))
            sign=subprocess.run([sys.executable,'-m','aleph_policy_sync','sign',
                                 '--policy',str(raw),'--private-key',str(secret),
                                 '--device-id','edge-69','--sequence','1',
                                 '--output',str(release),'--confirm-replacement'],
                                env=env,capture_output=True,text=True)
            self.assertEqual(sign.returncode,0,sign.stderr)
            self.assertEqual(release.stat().st_mode & 0o777,0o600)
            check=subprocess.run([sys.executable,'-m','aleph_policy_sync','verify',
                                  '--snapshot',str(release),'--device-id','edge-69',
                                  '--trust-dir',str(trust)],env=env,capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stderr)
            self.assertTrue(json.loads(check.stdout)['verified'])
            same=subprocess.run([sys.executable,'-m','aleph_policy_sync','sign',
                                 '--policy',str(raw),'--private-key',str(secret),
                                 '--device-id','edge-69','--sequence','1',
                                 '--output',str(release),'--confirm-replacement'],
                                env=env,capture_output=True,text=True)
            self.assertEqual(same.returncode,2)
            self.assertIn('refusing to replace',same.stderr)

if __name__=='__main__':unittest.main()
