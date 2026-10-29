"""Fault-injection tests exercise the real on-disk transaction, not shell restarts."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from dns_agent.transaction import Agent, Store, ApplyError, RecoveryError
from test_policy import NOW, sample

class FakeRuntime:
    """Only replaces the OS service boundary. Real Store and Agent execute."""
    def __init__(self):
        self.running = None
        self.fail_start = 0
        self.fail_validate = False
        self.starts = 0
        self.force_unhealthy = False
    def validate(self, path):
        if self.fail_validate: raise RuntimeError('invalid dnsmasq configuration')
    def start(self, path):
        self.starts += 1
        if self.fail_start:
            self.fail_start -= 1
            raise RuntimeError('injected unhealthy DNS process')
        self.running = path.read_text()
    def stop(self): self.running = None
    def alive(self): return self.running is not None
    def healthy(self): return self.alive() and not self.force_unhealthy

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state'
        self.store = Store(self.path); self.store.__enter__()
        self.runtime = FakeRuntime()
        self.agent = Agent(self.store, self.runtime, port=35353,
                           upstream='127.0.0.1', upstream_port=35453)
    def tearDown(self):
        self.runtime.stop(); self.store.__exit__(None,None,None); self.temp.cleanup()
    def apply(self, obj=None, now=NOW):
        return self.agent.cycle(json.dumps(obj or sample()).encode(), now=now)
    def test_first_apply_and_idempotency(self):
        self.apply(); before=self.runtime.starts
        self.apply()
        self.assertEqual(self.runtime.starts,before)
        self.assertIn('address=/blocked.test/',self.runtime.running)
        self.assertFalse((self.path/'pending.json').exists())
    def test_invalid_input_leaves_old_policy_but_expiry_still_runs(self):
        self.apply()
        self.agent.cycle(b'invalid',now=NOW+timedelta(minutes=1))
        self.assertIn('address=/blocked.test/',self.runtime.running)
        self.agent.cycle(b'invalid',now=NOW+timedelta(minutes=31))
        self.assertNotIn('address=/blocked.test/',self.runtime.running)
    def test_equal_issuance_changed_payload_and_replay_rejected(self):
        self.apply(); p=sample(); p['rules']=[]
        self.agent.cycle(json.dumps(p).encode(),now=NOW)
        self.assertIn('address=/blocked.test/',self.runtime.running)
        p['issued_at']='2029-12-31T23:59:00Z'
        self.agent.cycle(json.dumps(p).encode(),now=NOW)
        self.assertIn('address=/blocked.test/',self.runtime.running)
    def test_newer_empty_policy_revokes(self):
        self.apply(); p=sample(); p['rules']=[]; p['issued_at']='2030-01-01T00:01:00Z'
        self.apply(p,now=NOW+timedelta(minutes=1))
        self.assertNotIn('address=/blocked.test/',self.runtime.running)
    def test_failed_health_restores_config_and_state(self):
        self.apply(); oldstate=(self.path/'state.json').read_bytes(); oldconfig=self.runtime.running
        p=sample(); p['rules']=[]; p['issued_at']='2030-01-01T00:01:00Z'
        self.runtime.fail_start=1
        with self.assertRaises(ApplyError): self.apply(p,now=NOW+timedelta(minutes=1))
        self.assertEqual((self.path/'state.json').read_bytes(),oldstate)
        self.assertEqual(self.runtime.running,oldconfig)
        self.assertFalse((self.path/'pending.json').exists())
    def test_failed_rollback_retains_journal_and_is_fatal(self):
        self.apply(); self.runtime.fail_start=2
        p=sample(); p['rules']=[]; p['issued_at']='2030-01-01T00:01:00Z'
        with self.assertRaises(RecoveryError): self.apply(p,now=NOW+timedelta(minutes=1))
        self.assertTrue((self.path/'pending.json').is_file())
        self.assertIsNone(self.runtime.running)
    def test_configuration_check_fails_before_any_change(self):
        self.apply(); old=(self.path/'active.conf').read_bytes(); self.runtime.fail_validate=True
        p=sample(); p['rules']=[]; p['issued_at']='2030-01-01T00:01:00Z'
        with self.assertRaises(ApplyError): self.apply(p,now=NOW+timedelta(minutes=1))
        self.assertEqual((self.path/'active.conf').read_bytes(),old)
        self.assertTrue(self.runtime.alive())
    def test_lock_excludes_second_writer(self):
        with self.assertRaisesRegex(RuntimeError,'lock'):
            with Store(self.path): pass
    def test_state_file_symlink_is_rejected(self):
        target=Path(self.temp.name)/'outside'; target.write_text('do not overwrite')
        (self.path/'state.json').symlink_to(target)
        with self.assertRaises((OSError,RuntimeError)): self.apply()
        self.assertEqual(target.read_text(),'do not overwrite')
    def test_journal_recovers_interrupted_transaction(self):
        self.apply(); old=self.store.read_state()
        self.store.write_json('pending.json',{'previous':old})
        self.store.write_text('active.conf','wrong config\n')
        self.store.write_json('state.json',{'wrong':'state'})
        self.store.recover()
        self.assertEqual(self.store.read_state(),old)
        self.assertEqual((self.path/'active.conf').read_text(),old['config'])
    def test_unhealthy_but_alive_runtime_is_restarted(self):
        self.apply()
        previous_starts = self.runtime.starts
        self.runtime.force_unhealthy = True
        self.assertTrue(self.runtime.alive())
        result = self.apply()
        self.runtime.force_unhealthy = False
        self.assertEqual(result['event'], 'applied')
        self.assertEqual(self.runtime.starts, previous_starts + 1)
        self.assertIn('address=/blocked.test/', self.runtime.running)

    def test_candidate_stage_error_preserves_live_dns(self):
        self.apply()
        old_state = (self.path/'state.json').read_bytes()
        old_config = self.runtime.running
        starts = self.runtime.starts
        candidate = sample()
        candidate['issued_at'] = '2030-01-01T00:01:00Z'
        candidate['rules'] = []
        real_write = self.store.write_text

        def disk_error(name, value):
            if name == 'candidate.conf':
                raise OSError('injected disk failure before service stop')
            return real_write(name, value)

        with patch.object(self.store, 'write_text', side_effect=disk_error):
            with self.assertRaisesRegex(ApplyError, 'preflight'):
                self.apply(candidate, now=NOW+timedelta(minutes=1))
        self.assertEqual((self.path/'state.json').read_bytes(), old_state)
        self.assertEqual(self.runtime.running, old_config)
        self.assertEqual(self.runtime.starts, starts)
        self.assertFalse((self.path/'pending.json').exists())

    def test_pending_journal_write_error_preserves_live_dns(self):
        self.apply()
        old_state = (self.path/'state.json').read_bytes()
        old_config = self.runtime.running
        starts = self.runtime.starts
        candidate = sample()
        candidate['issued_at'] = '2030-01-01T00:01:00Z'
        candidate['rules'] = []
        real_write = self.store.write_json

        def disk_error(name, value):
            if name == 'pending.json':
                raise OSError('injected failure during rollback journal save')
            return real_write(name, value)

        with patch.object(self.store, 'write_json', side_effect=disk_error):
            with self.assertRaisesRegex(ApplyError, 'journal'):
                self.apply(candidate, now=NOW+timedelta(minutes=1))
        self.assertEqual((self.path/'state.json').read_bytes(), old_state)
        self.assertEqual(self.runtime.running, old_config)
        self.assertEqual(self.runtime.starts, starts)
        self.assertFalse((self.path/'candidate.conf').exists())

    def test_symlinked_candidate_journal_is_rejected_without_service_outage(self):
        self.apply()
        protected = Path(self.temp.name)/'outside'
        protected.write_text('do not modify')
        (self.path/'pending.json').symlink_to(protected)
        old = (self.path/'state.json').read_bytes()
        candidate = sample()
        candidate['issued_at'] = '2030-01-01T00:01:00Z'
        candidate['rules'] = []
        with self.assertRaisesRegex(ApplyError, 'journal'):
            self.apply(candidate, now=NOW+timedelta(minutes=1))
        self.assertTrue(self.runtime.alive())
        self.assertIn('address=/blocked.test/', self.runtime.running)
        self.assertEqual((self.path/'state.json').read_bytes(), old)
        self.assertEqual(protected.read_text(), 'do not modify')

    def test_symlinked_metadata_journal_is_rejected_without_service_outage(self):
        self.apply()
        protected = Path(self.temp.name)/'outside'
        protected.write_text('do not modify')
        (self.path/'pending.json').symlink_to(protected)
        old = (self.path/'state.json').read_bytes()
        candidate = sample()
        candidate['issued_at'] = '2030-01-01T00:01:00Z'
        candidate['rules'][0]['evidence'] = 'reviewed-again'
        with self.assertRaisesRegex(ApplyError, 'metadata journal'):
            self.apply(candidate, now=NOW+timedelta(minutes=1))
        self.assertTrue(self.runtime.alive())
        self.assertIn('address=/blocked.test/', self.runtime.running)
        self.assertEqual((self.path/'state.json').read_bytes(), old)
        self.assertEqual(protected.read_text(), 'do not modify')

    def test_staging_error_after_rule_expiration_does_not_keep_expired_block(self):
        self.apply()
        now = NOW+timedelta(minutes=31)
        with patch.object(self.store, 'write_text', side_effect=OSError('read-only disk')):
            with self.assertRaises(RecoveryError):
                self.agent.cycle(None, now=now)
        self.assertFalse(self.runtime.alive())

    def test_dead_runtime_is_not_mistaken_for_idempotent_success(self):
        self.apply(); self.runtime.stop(); count=self.runtime.starts
        self.apply(); self.assertEqual(self.runtime.starts,count+1)
    def test_metadata_only_update_does_not_restart_dns(self):
        self.apply()
        starts = self.runtime.starts
        old = self.store.read_state()['policy_sha256']
        policy = sample()
        policy['issued_at'] = '2030-01-01T00:01:00Z'
        policy['rules'][0]['evidence'] = 'reviewed-again'
        result = self.apply(policy, now=NOW+timedelta(minutes=1))
        self.assertEqual(result['event'], 'metadata_updated')
        self.assertEqual(self.runtime.starts, starts)
        self.assertNotEqual(self.store.read_state()['policy_sha256'], old)
        self.assertFalse((self.path/'pending.json').exists())

    def test_metadata_journal_failure_keeps_live_dns(self):
        self.apply()
        old_state = (self.path/'state.json').read_bytes()
        starts = self.runtime.starts
        candidate = sample()
        candidate['issued_at'] = '2030-01-01T00:01:00Z'
        candidate['rules'][0]['evidence'] = 'new-approval'
        with patch.object(self.store, 'write_json', side_effect=OSError('injected disk full')):
            with self.assertRaisesRegex(ApplyError, 'metadata journal unavailable'):
                self.apply(candidate, now=NOW+timedelta(minutes=1))
        self.assertEqual((self.path/'state.json').read_bytes(), old_state)
        self.assertTrue(self.runtime.alive())
        self.assertEqual(self.runtime.starts, starts)

    def test_metadata_write_failure_restores_state_without_dns_restart(self):
        self.apply()
        initial = (self.path/'state.json').read_bytes()
        starts = self.runtime.starts
        policy = sample()
        policy['issued_at'] = '2030-01-01T00:01:00Z'
        policy['rules'][0]['evidence'] = 'reviewed-again'
        write_original = self.store.write_json
        fail_once = [True]
        def failing_write(name, data):
            if name == 'state.json' and fail_once[0]:
                fail_once[0] = False
                raise OSError('injected disk failure')
            return write_original(name, data)
        with patch.object(self.store, 'write_json', side_effect=failing_write):
            with self.assertRaises(ApplyError):
                self.apply(policy, now=NOW+timedelta(minutes=1))
        self.assertEqual((self.path/'state.json').read_bytes(), initial)
        self.assertEqual(self.runtime.starts, starts)
        self.assertFalse((self.path/'pending.json').exists())

    def test_clock_does_not_resurrect_expired_rules_after_restart(self):
        self.apply(now=NOW)
        self.agent.cycle(None, now=NOW+timedelta(minutes=31))
        self.assertNotIn('address=/blocked.test/', self.runtime.running)
        restarted = Agent(self.store, self.runtime, port=35353,
                          upstream='127.0.0.1', upstream_port=35453)
        restarted.cycle(None, now=NOW+timedelta(minutes=1))
        self.assertNotIn('address=/blocked.test/', self.runtime.running)
        self.assertGreaterEqual(
            self.store.read_state()['applied_at'], '2030-01-01T00:31:00')

    def test_clock_does_not_resurrect_expired_rules_in_process(self):
        self.apply(now=NOW+timedelta(minutes=31))
        self.apply(now=NOW)
        self.assertNotIn('address=/blocked.test/',self.runtime.running)
    def test_expired_rules_are_not_restored_after_failed_refresh(self):
        self.apply(); self.runtime.fail_start=1
        with self.assertRaises(RecoveryError):
            self.agent.cycle(b'invalid',now=NOW+timedelta(minutes=31))
        self.assertFalse(self.runtime.alive())
    def test_state_config_drift_is_not_an_idempotent_success(self):
        self.apply(); self.store.write_text('active.conf','unexpected manual edit\n')
        with self.assertRaises(RecoveryError): self.apply()
    def test_corrupted_policy_digest_is_not_used_as_a_new_policy(self):
        self.apply()
        original = self.store.read_state()
        damaged = copy.deepcopy(original)
        damaged['policy'] = damaged['policy'].replace('blocked.test', 'different.test')
        self.store.write_json('state.json', damaged)
        self.assertEqual((self.path / 'active.conf').read_text(), original['config'])
        with self.assertRaisesRegex(RecoveryError, 'state/config inconsistency'):
            self.agent.cycle(None, now=NOW + timedelta(seconds=5))
        self.assertTrue(self.runtime.alive())
        self.assertIn('address=/blocked.test/', self.runtime.running)

    def test_corrupt_recovery_journal_does_not_overwrite_live_state(self):
        self.apply()
        original = self.store.read_state()
        damaged = copy.deepcopy(original)
        damaged['policy'] = damaged['policy'].replace('blocked.test', 'different.test')
        self.store.write_json('pending.json', {'previous': damaged})
        with self.assertRaisesRegex(RecoveryError, 'interrupted transaction'):
            self.store.recover()
        self.assertEqual(self.store.read_state(), original)
        self.assertTrue((self.path / 'pending.json').is_file())

    def test_initial_invalid_policy_does_not_start_service(self):
        with self.assertRaises(ApplyError): self.agent.cycle(b'invalid',now=NOW)
        self.assertFalse(self.runtime.alive())

if __name__ == '__main__': unittest.main()
