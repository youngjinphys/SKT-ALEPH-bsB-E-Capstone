"""Ownership checks for the installed nftables guard."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[2] / 'infra' / 'edge' / 'firewall_guard.py'
spec = importlib.util.spec_from_file_location('firewall_guard', path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class FirewallGuardTests(unittest.TestCase):
    def test_legacy_table_requires_exact_unmarked_rules(self):
        config = {'token': '0' * 32, 'listen': '192.168.44.10',
                  'interface': 'eth0', 'subnet': '192.168.44.0/24'}
        entries = guard.expected(config)
        entries[0]['table']['handle'] = 17
        for item in entries:
            if 'rule' in item:
                del item['rule']['comment']
        self.assertEqual(guard.checked_legacy_handle(config, entries), 17)
        entries[-1]['rule']['expr'].append({'accept': None})
        with self.assertRaisesRegex(RuntimeError, 'ownership'):
            guard.checked_legacy_handle(config, entries)

    def test_existing_foreign_table_is_never_replaced(self):
        config = {'token': '0' * 32, 'listen': '192.168.44.10',
                  'interface': 'eth0', 'subnet': '192.168.44.0/24'}
        foreign = [{'table': {'family': 'inet', 'name': 'aleph_dns', 'handle': 1}}]
        with patch.object(guard, 'snapshot', return_value=(1, foreign)), \
             patch.object(guard, 'run_nft') as nft:
            with self.assertRaisesRegex(RuntimeError, 'ownership'):
                guard.apply(config)
            nft.assert_not_called()

    def test_modified_owned_table_is_never_deleted(self):
        config = {'token': '0' * 32, 'listen': '192.168.44.10',
                  'interface': 'eth0', 'subnet': '192.168.44.0/24'}
        foreign = [{'table': {'family': 'inet', 'name': 'aleph_dns', 'handle': 1,
                              'comment': 'skt-aleph-dns-v1:' + config['token']}},
                   {'chain': {'family': 'inet', 'table': 'aleph_dns', 'name': 'foreign'}}]
        with patch.object(guard, 'snapshot', return_value=(1, foreign)), \
             patch.object(guard, 'delete_with_generation') as delete:
            with self.assertRaisesRegex(RuntimeError, 'ownership'):
                guard.remove(config)
            delete.assert_not_called()

    def test_apply_rejects_kernel_without_generation_guard_before_creation(self):
        config = {'token': '0' * 32, 'listen': '192.168.44.10',
                  'interface': 'eth0', 'subnet': '192.168.44.0/24'}
        with patch.object(guard, 'snapshot', return_value=(1, [])), \
             patch.object(guard, 'require_generation_guard', side_effect=RuntimeError('unsupported')), \
             patch.object(guard, 'run_nft') as nft:
            with self.assertRaisesRegex(RuntimeError, 'unsupported'):
                guard.apply(config)
            nft.assert_not_called()

    def test_zero_generation_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'zero'):
            guard.require_generation_guard(0)

    def test_unsupported_generation_guard_is_rejected(self):
        import struct
        # An acknowledgement of the create means the kernel ignored the guard.
        fake = struct.pack('IHHIIi', 20, 2, 0, 3, 0, 0)
        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def send(self, data): pass
            def recv(self, size): return fake
        with patch.object(guard, 'netlink_socket', return_value=FakeSocket()):
            with self.assertRaisesRegex(RuntimeError, 'did not reject'):
                guard.require_generation_guard(1)


def namespace_flags(euid):
    # A new user namespace maps only root when invoked by root, making files
    # under a private user home inaccessible. Root needs only a network namespace.
    return ['-n'] if euid == 0 else ['-Urn']


class NftNamespaceTests(unittest.TestCase):
    def test_namespace_flags_preserve_root_filesystem_access(self):
        self.assertEqual(namespace_flags(0), ['-n'])
        self.assertEqual(namespace_flags(1000), ['-Urn'])

    def test_real_nft_lifecycle_and_conflicts(self):
        import os
        import shutil
        import subprocess
        import sys
        required = os.environ.get('ALEPH_REQUIRE_NETNS_TESTS') == '1'
        unshare = shutil.which('unshare')
        nft = Path('/usr/sbin/nft')
        if not unshare or not nft.exists():
            if required: self.fail('unshare and nft are required for isolated tests')
            self.skipTest('unshare or nft unavailable')
        flags = namespace_flags(os.geteuid())
        probe = subprocess.run([unshare, *flags, '/usr/sbin/nft', '-f', '/dev/stdin'],
                               input='add table inet aleph_probe\ndelete table inet aleph_probe\n',
                               capture_output=True, text=True)
        if probe.returncode:
            if required: self.fail('nftables mutation unavailable inside network namespace: ' + probe.stderr)
            self.skipTest('nftables mutation unavailable: ' + probe.stderr.strip())
        result = subprocess.run([unshare, *flags, sys.executable,
                                 str(path.parent.parent.parent / 'tests' / 'deployment' / 'nft_namespace_scenarios.py')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
