"""Root-only application and replay tests. Never touches the real DNS service."""
from datetime import timedelta
import hashlib
import json
import os
import sys
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

    def test_prepared_intent_is_durable_before_publish(self):
        self.staged()
        def fail_after_journal(_):
            intent = json.loads((self.state/'pending-apply.json').read_bytes())
            self.assertEqual(intent['format'], 1)
            self.assertEqual(intent['sequence'], 1)
            self.assertEqual(intent['policy_sha256'], intent['policy_sha256'].lower())
            self.assertFalse((self.state/'applied.json').exists())
            raise SyncError('simulated outage after intent persisted')
        with self.assertRaisesRegex(SyncError, 'simulated outage'):
            self.apply(publisher=fail_after_journal)
        self.assertTrue((self.state/'pending-apply.json').is_file())
        self.assertFalse((self.state/'applied.json').exists())
        self.assertEqual(self.apply(), 'applied')
        self.assertFalse((self.state/'pending-apply.json').exists())

    def test_pending_intent_rejects_newer_signed_release_until_retry(self):
        self.staged()
        def fail(_): raise SyncError('first release did not finish')
        with self.assertRaises(SyncError):
            self.apply(publisher=fail)
        later = NOW + timedelta(minutes=1)
        self.staged(sequence=2, at=later)
        with self.assertRaisesRegex(SyncError, 'no verified fallback'):
            self.apply(when=later, attestor=lambda _: (_ for _ in ()).throw(SyncError('DNS not published')))
        self.assertEqual(self.published, [])
        self.staged(sequence=1)
        self.assertEqual(self.apply(), 'applied')
        self.staged(sequence=2, at=later)
        self.assertEqual(self.apply(when=later), 'applied')
        self.assertEqual(len(self.published), 2)

    def test_pending_intent_rejects_same_sequence_with_different_payload(self):
        self.staged()
        def fail(_): raise SyncError('injected first publish failure')
        with self.assertRaises(SyncError):
            self.apply(publisher=fail)
        altered = policy()
        altered['rules'][0]['domain'] = 'replacement.example'
        self.staged(data=altered)
        with self.assertRaisesRegex(SyncError, 'unfinished signed-policy'):
            self.apply()
        self.assertEqual(self.published, [])

    def test_failing_intent_write_never_invokes_publisher(self):
        from aleph_policy_sync import sync as module
        self.staged()
        original = module.atomic_private
        def fail_first(path, data, *, owner):
            if path.name == 'pending-apply.json':
                raise OSError('simulated disk error while saving intent')
            return original(path, data, owner=owner)
        with patch.object(module, 'atomic_private', side_effect=fail_first):
            with self.assertRaisesRegex(OSError, 'disk error'):
                self.apply()
        self.assertEqual(self.published, [])
        self.assertFalse((self.state/'applied.json').exists())
        self.assertFalse((self.state/'pending-apply.json').exists())

    def test_commit_write_failure_after_dns_publish_is_recoverable(self):
        from aleph_policy_sync import sync as module
        self.staged()
        original = module.atomic_private
        def fail_commit(path, data, *, owner):
            if path.name == 'applied.json':
                raise OSError('simulated disk-full after DNS accepted policy')
            return original(path, data, owner=owner)
        with patch.object(module, 'atomic_private', side_effect=fail_commit):
            with self.assertRaisesRegex(OSError, 'disk-full'):
                self.apply()
        self.assertEqual(len(self.published), 1)
        self.assertTrue((self.state/'pending-apply.json').is_file())
        self.assertFalse((self.state/'applied.json').exists())
        self.assertEqual(self.apply(), 'applied')
        self.assertFalse((self.state/'pending-apply.json').exists())
        self.assertEqual(json.loads((self.state/'applied.json').read_text())['sequence'], 1)

    def test_committed_watermark_can_clean_up_interrupted_journal(self):
        from aleph_policy_sync import sync as module
        self.staged()
        with patch.object(module, '_delete_intent', side_effect=OSError('injected interrupted cleanup')):
            with self.assertRaises(OSError):
                self.apply()
        self.assertTrue((self.state/'pending-apply.json').is_file())
        self.assertEqual(json.loads((self.state/'applied.json').read_text())['sequence'], 1)
        before = len(self.published)
        self.assertEqual(self.apply(), 'already-applied')
        self.assertEqual(len(self.published), before)
        self.assertFalse((self.state/'pending-apply.json').exists())
        self.assertEqual(len(self.attested), 1)

    def test_committed_pending_cleanup_before_newer_release_requires_live_attestation(self):
        from aleph_policy_sync import sync as module
        self.staged()
        with patch.object(module, '_delete_intent', side_effect=OSError('simulated cleanup failure')):
            with self.assertRaises(OSError):
                self.apply()
        prior = json.loads((self.state/'applied.json').read_text())
        later = NOW + timedelta(minutes=1)
        self.staged(sequence=2, at=later)
        def reject(_): raise SyncError('previous DNS state not healthy')
        with self.assertRaisesRegex(SyncError, 'not healthy'):
            self.apply(when=later, attestor=reject)
        self.assertTrue((self.state/'pending-apply.json').exists())
        self.assertEqual(len(self.published), 1)
        self.assertEqual(self.apply(when=later), 'applied')
        self.assertEqual(self.attested, [prior['policy_sha256']])
        self.assertFalse((self.state/'pending-apply.json').exists())

    def test_new_release_repairs_previous_pending_success_before_advancing(self):
        from aleph_policy_sync import sync as module
        self.staged()
        actual = module.atomic_private
        def fail_local_commit(path, data, *, owner):
            if path.name == 'applied.json':
                raise OSError('publish accepted but local disk failed')
            return actual(path, data, owner=owner)
        with patch.object(module, 'atomic_private', side_effect=fail_local_commit):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(len(self.published), 1)
        self.assertFalse((self.state/'applied.json').exists())
        later = NOW + timedelta(minutes=1)
        self.staged(sequence=2, at=later)
        # First attestation must prove seq1 reached the local DNS before seq2.
        old_policy = json.loads(self.published[0])
        def confirm_old(digest):
            from dns_agent.policy import parse_policy
            self.assertEqual(digest, parse_policy(json.dumps(old_policy).encode(), now=later).digest)
            self.attested.append(digest)
        self.assertEqual(self.apply(when=later, attestor=confirm_old), 'applied')
        self.assertEqual(len(self.published), 2)
        self.assertEqual(json.loads((self.state/'applied.json').read_text())['sequence'], 2)
        self.assertFalse((self.state/'pending-apply.json').exists())
        self.assertEqual(len(self.attested), 1)

    def test_orphaned_unpublished_intent_can_be_abandoned_only_with_prior_dns_attestation(self):
        self.staged()
        self.apply()
        previous = json.loads((self.state/'applied.json').read_text())
        later = NOW + timedelta(minutes=1)
        self.staged(sequence=2, at=later)
        def fail_publish(_):
            raise SyncError('DNS candidate was never accepted')
        with self.assertRaises(SyncError):
            self.apply(when=later, publisher=fail_publish)
        self.staged(sequence=3, at=later + timedelta(seconds=1))
        checked = []
        def status(digest):
            checked.append(digest)
            if digest != previous['policy_sha256']:
                raise SyncError('pending candidate is not live')
        self.assertEqual(self.apply(when=later + timedelta(seconds=1), attestor=status), 'applied')
        self.assertEqual(len(checked), 2)
        self.assertEqual(checked[-1], previous['policy_sha256'])
        self.assertEqual(json.loads((self.state/'applied.json').read_text())['sequence'], 3)
        self.assertFalse((self.state/'pending-apply.json').exists())

    def test_neither_pending_nor_prior_live_requires_operator_recovery(self):
        self.staged()
        self.apply()
        later = NOW + timedelta(minutes=1)
        self.staged(sequence=2, at=later)
        with self.assertRaises(SyncError):
            self.apply(when=later, publisher=lambda _: (_ for _ in ()).throw(SyncError('DNS not reached')))
        self.staged(sequence=3, at=later + timedelta(seconds=1))
        checked = []
        def offline(digest):
            checked.append(digest)
            raise SyncError('DNS unavailable')
        with self.assertRaisesRegex(SyncError, 'DNS unavailable'):
            self.apply(when=later + timedelta(seconds=1), attestor=offline)
        self.assertEqual(len(checked), 2)
        self.assertTrue((self.state/'pending-apply.json').is_file())
        self.assertEqual(json.loads((self.state/'applied.json').read_text())['sequence'], 1)

    def test_untrusted_intent_file_symlink_is_rejected(self):
        self.staged()
        outside = self.root/'outside-intent.json'
        outside.write_text('PRESERVE')
        (self.state/'pending-apply.json').symlink_to(outside)
        with self.assertRaises(OSError):
            self.apply()
        self.assertEqual(outside.read_text(), 'PRESERVE')
        self.assertEqual(self.published, [])

    def test_malformed_pending_intent_does_not_allow_publish(self):
        self.staged()
        pending = self.state/'pending-apply.json'
        pending.write_text('{"sequence": 1}')
        pending.chmod(0o600)
        with self.assertRaisesRegex(SyncError, 'invalid pending'):
            self.apply()
        self.assertEqual(self.published, [])

    def test_group_readable_pending_intent_is_rejected_before_publish(self):
        self.staged()
        pending = self.state/'pending-apply.json'
        pending.write_text('{"sequence": 1}')
        pending.chmod(0o640)
        with self.assertRaises(SnapshotError):
            self.apply()
        self.assertEqual(self.published, [])

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
        # Some distributions symlink /usr/bin/env; the admin guard must
        # require the resolved *regular*, root-owned executable instead.
        self.assertTrue(_safe_root_program(Path(sys.executable).resolve()).is_file())
        with self.assertRaisesRegex(SyncError, 'absolute'):
            _safe_root_program(Path('relative-admin.py'))

if __name__=='__main__':unittest.main()
