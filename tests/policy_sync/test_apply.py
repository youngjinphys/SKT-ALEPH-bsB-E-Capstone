"""Root-only application and replay tests. Never touches the real DNS service."""
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import pwd
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aleph_policy_sync.snapshot import SnapshotError, canonical, sign_policy
from aleph_policy_sync.sync import SyncError, apply_once, _safe_root_program
from test_snapshot import NOW, policy, trust


@unittest.skipUnless(os.geteuid()==0,'Root apply lifecycle requires root fixture')
class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.fetch_user='nobody'
        self.fetch_uid=pwd.getpwnam('nobody').pw_uid
        self.inbox=self.root/'inbox';self.inbox.mkdir(mode=0o700)
        os.chown(self.inbox, self.fetch_uid, self.fetch_uid)
        self.state=self.root/'state';self.state.mkdir(mode=0o700)
        self.trust=self.root/'trust';self.trust.mkdir(mode=0o700)
        self.key=Ed25519PrivateKey.generate();trust(self.trust,self.key)
        self.published=[]
        self.attested=[]
    def staged(self, *, sequence=1, at=NOW, data=None, key=None, confirm_empty=False):
        k=key or self.key
        blob=canonical(sign_policy(canonical(data if data is not None else policy(at)),k,
                                   target='edge-69',sequence=sequence,signed_at=at,
                                   confirm_empty=confirm_empty))+b'\n'
        path=self.inbox/'current.json';path.write_bytes(blob)
        path.chmod(0o600);os.chown(path,self.fetch_uid,self.fetch_uid)
        return blob
    def apply(self, *, when=NOW, publisher=None, attestor=None):
        if publisher is None:
            def publisher(p):
                self.published.append(p.read_bytes())
        if attestor is None:
            def attestor(digest):
                self.attested.append(digest)
        return apply_once(device='edge-69',trust_dir=self.trust,inbox_dir=self.inbox,
                          fetch_user=self.fetch_user,state_dir=self.state,
                          dns_admin=Path('/usr/bin/python3'),now=when,
                          publisher=publisher,attestor=attestor)

    def test_valid_signed_snapshot_publishes_then_persists_sequence(self):
        self.staged()
        self.assertEqual(self.apply(),'applied')
        self.assertEqual(len(self.published),1)
        self.assertEqual(json.loads(self.published[0])['rules'][0]['domain'],'blocked.example')
        meta=json.loads((self.state/'applied.json').read_text())
        self.assertEqual(meta['sequence'],1)
        self.assertEqual((self.state/'applied.json').stat().st_mode & 0o777,0o600)
        self.assertFalse((self.state/'pending-policy.json').exists())
        self.assertEqual(self.apply(),'already-applied')
        self.assertEqual(len(self.published),1)
        self.assertEqual(self.attested, [meta['policy_sha256']])

    def test_real_attestation_command_is_bounded_and_read_only(self):
        from aleph_policy_sync.sync import _locked_attest
        from types import SimpleNamespace
        with patch('aleph_policy_sync.sync._safe_root_program', return_value=Path('/opt/aleph-dns/admin.py')), \
             patch('aleph_policy_sync.sync.subprocess.run') as command:
            _locked_attest(Path('/opt/aleph-dns/admin.py'), 'a' * 64)
            args, opts = command.call_args
            self.assertEqual(args[0][3:5], ['attest', '--policy-sha256'])
            self.assertEqual(args[0][-1], 'a' * 64)
            self.assertTrue(opts['check'])
            self.assertEqual(opts['timeout'], 30)
            self.assertEqual(opts['stdin'], __import__('subprocess').DEVNULL)
        with self.assertRaisesRegex(SyncError, 'invalid expected'):
            _locked_attest(Path('/opt/aleph-dns/admin.py'), 'not-a-hash')

    def test_replayed_sequence_checks_live_dns_before_reporting_success(self):
        self.staged()
        self.assertEqual(self.apply(), 'applied')
        previous = (self.state/'applied.json').read_bytes()
        def offline_or_diverged(_):
            raise SyncError('simulated DNS policy drift')
        with self.assertRaisesRegex(SyncError, 'policy drift'):
            self.apply(attestor=offline_or_diverged)
        self.assertEqual((self.state/'applied.json').read_bytes(), previous)
        self.assertEqual(len(self.published), 1)
        self.assertFalse((self.state/'pending-policy.json').exists())
        self.assertEqual(self.apply(), 'already-applied')
        self.assertEqual(len(self.attested), 1)

    def test_failed_publish_does_not_advance_sequence_or_erase_last_policy(self):
        self.staged();self.apply();last=(self.state/'applied.json').read_bytes()
        later=NOW+timedelta(minutes=1)
        self.staged(sequence=2,at=later)
        def failure(_):raise SyncError('injected publication failure')
        with self.assertRaises(SyncError):self.apply(when=later,publisher=failure)
        self.assertEqual((self.state/'applied.json').read_bytes(),last)
        self.assertEqual(len(self.published),1)
        self.assertTrue((self.state/'pending-policy.json').exists())
        self.assertEqual(self.apply(when=later),'applied')
        self.assertEqual(len(self.published),2)

    def test_old_sequence_and_same_sequence_conflict_rejected(self):
        self.staged(sequence=2);self.apply()
        self.staged(sequence=1)
        with self.assertRaisesRegex(SyncError,'rollback'):
            self.apply()
        different=policy();different['rules'][0]['domain']='other.example'
        self.staged(sequence=2,data=different)
        with self.assertRaisesRegex(SyncError,'conflicting'):
            self.apply()
        self.assertEqual(len(self.published),1)

    def test_tampered_document_and_untrusted_signer_not_published(self):
        blob=self.staged()
        (self.inbox/'current.json').write_bytes(blob.replace(b'"sequence":1',b'"sequence":2'))
        os.chown(self.inbox/'current.json',self.fetch_uid,self.fetch_uid)
        with self.assertRaises(SnapshotError):self.apply()
        self.staged(key=Ed25519PrivateKey.generate())
        with self.assertRaises((SnapshotError,FileNotFoundError)):self.apply()
        self.assertEqual(self.published,[])

    def test_signed_withdraw_all_permitted_only_with_intent(self):
        self.staged(sequence=1)
        self.apply()
        later=NOW+timedelta(minutes=1)
        self.staged(sequence=2,at=later,data=policy(later,empty=True),confirm_empty=True)
        self.assertEqual(self.apply(when=later),'applied')
        self.assertEqual(json.loads(self.published[-1])['rules'],[])

    def test_expired_policy_not_applied_and_last_state_remains(self):
        self.staged();self.apply()
        previous=(self.state/'applied.json').read_bytes()
        later=NOW+timedelta(minutes=13)
        with self.assertRaisesRegex(SnapshotError,'expired'):
            self.apply(when=later)
        self.assertEqual((self.state/'applied.json').read_bytes(),previous)

    def test_symlinked_unprivileged_inbox_file_cannot_be_read(self):
        outside=self.root/'outside.json';outside.write_text('protected')
        path=self.inbox/'current.json';path.symlink_to(outside)
        with self.assertRaises(OSError):self.apply()
        self.assertEqual(self.published,[])
        self.assertEqual(outside.read_text(),'protected')

    def test_owner_check_prevents_other_spool_source(self):
        self.staged()
        os.chown(self.inbox/'current.json',0,0)
        with self.assertRaises(SnapshotError):self.apply()

    def test_clock_rollback_does_not_accept_future_sequence(self):
        self.staged();self.apply()
        later=NOW+timedelta(minutes=2)
        self.staged(sequence=2,at=later)
        self.apply(when=later)
        self.staged(sequence=3,at=later)
        with self.assertRaises((SyncError,SnapshotError)):
            self.apply(when=NOW)

    def test_root_admin_guard_rejects_untrusted_path(self):
        admin=self.root/'untrusted.py';admin.write_text('print("bad")')
        with self.assertRaises(SyncError):_safe_root_program(admin)
        self.assertTrue(_safe_root_program(Path('/usr/bin/env')).is_file())

if __name__=='__main__':unittest.main()
