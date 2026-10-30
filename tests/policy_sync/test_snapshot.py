"""Signed policy snapshot tests; no DNS sockets or external network."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from aleph_policy_sync.snapshot import (SnapshotError, canonical, device_id,
    load_private_key, load_public_key, public_key_id, sign_policy, strict_load,
    verify_envelope, trust_key)

NOW=datetime(2030,1,1,tzinfo=timezone.utc)


def policy(at=NOW, *, domain='blocked.example', empty=False):
    exp=(at+timedelta(minutes=12)).isoformat()
    return {'issued_at':(at-timedelta(seconds=5)).isoformat(),
            'expires_at':exp,
            'rules':[] if empty else [{'domain':domain,'scope':'SUBTREE','decision':'BLOCK',
                                      'approved':True,'expires_at':exp,'evidence':'reviewed-test'}]}


def trust(folder:Path,key):
    kid=public_key_id(key.public_key())
    pub=key.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo)
    (folder/(kid+'.pem')).write_bytes(pub)
    (folder/(kid+'.pem')).chmod(0o644)
    return kid


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.trust=self.root/'trust';self.trust.mkdir(mode=0o700)
        self.key=Ed25519PrivateKey.generate();self.kid=trust(self.trust,self.key)

    def signed(self, *, sequence=1, target='edge-69', data=None, at=NOW, confirm_empty=False):
        return sign_policy(canonical(data if data is not None else policy(at)),self.key,
                           sequence=sequence,target=target,signed_at=at,confirm_empty=confirm_empty)

    def verify(self, signed, *, when=NOW, device='edge-69'):
        return verify_envelope(canonical(signed),expected_device=device,
                               trust_dir=self.trust,now=when)

    def test_signature_roundtrip_and_policy_digest(self):
        env=self.signed();payload,parsed=self.verify(env)
        self.assertEqual(env['key_id'],self.kid)
        self.assertEqual(payload['sequence'],1)
        self.assertEqual(payload['policy_sha256'],parsed.digest)
        self.assertEqual(parsed.blocked(NOW),('blocked.example',))

    def test_envelope_mutations_and_signature_tamper_fail(self):
        env=self.signed()
        changes=[lambda e: e['payload'].update({'sequence':2}),
                 lambda e: e['payload']['policy']['rules'][0].update({'domain':'clean.example'}),
                 lambda e: e.update({'signature':'A'*86}),
                 lambda e: e['payload'].update({'valid_until':(NOW+timedelta(days=1)).isoformat()}),
                 lambda e: e.update({'key_id':'0'*64}),
                 lambda e: e.update({'other':1})]
        for fn in changes:
            item=json.loads(json.dumps(env));fn(item)
            with self.subTest(item=item['key_id'][:6]),self.assertRaises((SnapshotError,FileNotFoundError)):
                self.verify(item)

    def test_cross_device_and_untrusted_key_fail(self):
        with self.assertRaisesRegex(SnapshotError,'different device'):
            self.verify(self.signed(),device='edge-70')
        bad=self.signed();bad['key_id']='f'*64
        with self.assertRaises((SnapshotError,FileNotFoundError)):
            self.verify(bad)

    def test_expiry_and_future_timestamp(self):
        with self.assertRaisesRegex(SnapshotError,'expired'):
            self.verify(self.signed(),when=NOW+timedelta(minutes=13))
        with self.assertRaisesRegex(SnapshotError,'future'):
            self.verify(self.signed(at=NOW+timedelta(minutes=3)),when=NOW)
        # Old expired keys must still be verifiable during the next download cycle.
        payload,_=verify_envelope(canonical(self.signed()),expected_device='edge-69',
                                  trust_dir=self.trust,now=NOW+timedelta(minutes=13),
                                  allow_expired=True)
        self.assertEqual(payload['sequence'],1)

    def test_empty_policy_requires_explicit_withdrawal(self):
        data=policy(empty=True)
        with self.assertRaisesRegex(SnapshotError,'--confirm-empty'):
            self.signed(data=data)
        env=self.signed(data=data,confirm_empty=True)
        self.assertEqual(self.verify(env)[0]['intent'],'withdraw_all')
        env['payload']['intent']='replace'
        key=self.key
        env['signature']=base64.urlsafe_b64encode(key.sign(canonical(env['payload']))).decode().rstrip('=')
        with self.assertRaisesRegex(SnapshotError,'withdrawal'):
            self.verify(env)

    def test_strict_duplicate_keys_nonfinite_and_size(self):
        for blob in (b'{"a":1,"a":2}',b'{"x":NaN}',b'garbage',b'\xff',b' '*(2*1024*1024+1)):
            with self.subTest(blob=blob[:10]),self.assertRaises(SnapshotError):strict_load(blob)

    def test_sequence_device_and_policy_contract(self):
        for bad in (0,-1,True,1<<65,'2'):
            with self.subTest(seq=bad),self.assertRaises(SnapshotError):
                self.signed(sequence=bad)
        for bad in ('','a/b','.. bad','a'*65):
            with self.subTest(device=bad),self.assertRaises(SnapshotError):
                device_id(bad)
        broken=policy();broken['rules'][0]['scope']='EXACT'
        with self.assertRaises(SnapshotError):self.signed(data=broken)

    def test_private_key_file_mode_and_public_fingerprint(self):
        private=self.root/'secret.pem'
        private.write_bytes(self.key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        private.chmod(0o600)
        self.assertEqual(public_key_id(load_private_key(private).public_key()),self.kid)
        private.chmod(0o644)
        with self.assertRaisesRegex(SnapshotError,'ownership or mode'):
            load_private_key(private)
        public=self.trust/(self.kid+'.pem')
        self.assertEqual(public_key_id(load_public_key(public)),self.kid)
        public.rename(self.trust/'different.pem')
        (self.trust/(self.kid+'.pem')).symlink_to(self.trust/'different.pem')
        with self.assertRaises(OSError):trust_key(self.trust,self.kid)

if __name__=='__main__':unittest.main()
