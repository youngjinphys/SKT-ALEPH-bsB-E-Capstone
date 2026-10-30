"""System install safeguards and pure rendering; no privileged changes in tests."""
import importlib.util
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
import io
import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / 'infra' / 'edge' / 'system_dns.py'
spec = importlib.util.spec_from_file_location('system_dns', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SystemDnsTests(unittest.TestCase):
    def test_upgrade_rejects_parent_allow_before_migration(self):
        args = SimpleNamespace(apply=True, adopt_legacy_table=False)
        existing = {'legacy': False, 'options': ('192.168.7.69', 'eth0',
                                                  '192.168.7.0/24', '8.8.8.8', 53)}
        with tempfile.TemporaryDirectory() as work, \
             patch.object(mod, 'MIGRATION_JOURNAL', Path(work)/'journal'), \
             patch.object(mod, 'need_root'), patch.object(mod, 'publish_lock', return_value=11), \
             patch.object(mod, 'legacy_publish_lock', return_value=12), \
             patch.object(mod, 'inspect_existing', return_value=existing), \
             patch.object(mod, 'check_service_python'), \
             patch.object(mod, 'check_parent_ip_allows', side_effect=RuntimeError('parent allow')), \
             patch.object(mod, 'migrate_existing') as migrate, patch.object(mod.os, 'close'):
            with self.assertRaisesRegex(RuntimeError, 'parent allow'):
                mod.upgrade(args)
            migrate.assert_not_called()

    def test_unit_requires_mapless_guard_before_dns_start(self):
        dns, _ = mod.unit_files('192.168.7.69', '8.8.8.8', 53, '192.168.7.0/24')
        expected = ('ExecStartPre=+/usr/bin/python3 -B -m dns_agent.cgroup_guard '
                    '192.168.7.69 192.168.7.0/24 8.8.8.8')
        self.assertIn(expected, dns)
        self.assertLess(dns.index(expected), dns.index('ExecStart=/usr/bin/python3'))

    def test_install_rejects_incompatible_service_python_before_interface_changes(self):
        # The installer can be invoked by a different interpreter from the one
        # hard-coded into the service units. An unsupported service interpreter
        # must be detected before any service or firewall operations.
        args = SimpleNamespace()
        old_python = SimpleNamespace(returncode=1, stdout='', stderr='')
        with patch.object(mod.Path, 'exists', return_value=False), \
             patch.object(mod.Path, 'is_symlink', return_value=False), \
             patch.object(mod.Path, 'is_file', return_value=True), \
             patch.object(mod.shutil, 'which', return_value='/usr/bin/tool'), \
             patch.object(mod.subprocess, 'run', return_value=old_python), \
             patch.object(mod, 'inspect_interface', side_effect=AssertionError('preflight missed')):
            with self.assertRaisesRegex(RuntimeError, 'service Python'):
                mod._install_locked(args, '192.168.44.10', 'eth0', '192.168.44.0/24',
                                    '1.1.1.1', 53, None, '', '', '', '')

    def test_service_interpreter_preflight_runs_the_real_python(self):
        # This is the same executable and isolated mode used by the unit preflight.
        mod.check_service_python()

    def test_service_interpreter_preflight_rejects_unavailable_or_hung_interpreter(self):
        for error in (FileNotFoundError('missing'), subprocess.TimeoutExpired('/usr/bin/python3', 5)):
            with self.subTest(error=type(error).__name__), \
                 patch.object(mod.subprocess, 'run', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, 'unable to execute service Python'):
                    mod.check_service_python()

    def test_root_group_must_have_no_nonroot_members(self):
        root = SimpleNamespace(pw_uid=0, pw_gid=0)
        other = SimpleNamespace(pw_uid=1000, pw_gid=1000)
        with patch.object(mod.grp, 'getgrgid', return_value=SimpleNamespace(gr_mem=['root'])), \
             patch.object(mod.pwd, 'getpwnam', return_value=root), \
             patch.object(mod.pwd, 'getpwall', return_value=[root, other]):
            self.assertTrue(mod.root_group_exclusive())
        with patch.object(mod.grp, 'getgrgid', return_value=SimpleNamespace(gr_mem=['root', 'other'])), \
             patch.object(mod.pwd, 'getpwnam', side_effect=[root, other]), \
             patch.object(mod.pwd, 'getpwall', return_value=[root, other]):
            self.assertFalse(mod.root_group_exclusive())

    def test_legacy_source_rejects_access_and_default_acls(self):
        info = SimpleNamespace(st_mode=0o040775, st_uid=0, st_gid=0)
        with patch.object(mod, 'root_group_exclusive', return_value=True), \
             patch.object(mod.os, 'listxattr', return_value=[]):
            self.assertTrue(mod.historical_source_permissions(Path('/unused'), info))
        for acl in ('system.posix_acl_access', 'system.posix_acl_default'):
            with self.subTest(acl=acl), patch.object(mod, 'root_group_exclusive', return_value=True), \
                 patch.object(mod.os, 'listxattr', return_value=[acl]):
                self.assertFalse(mod.historical_source_permissions(Path('/unused'), info))

    def test_unknown_old_code_inventory_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base/'src').mkdir(mode=0o755)
            (base/'src'/'unexpected').write_text('retain')
            (base/'src'/'unexpected').chmod(0o644)
            with patch.object(mod, 'CODE', base/'src'):
                with self.assertRaisesRegex(RuntimeError, 'historical'):
                    mod.verify_historical_code(legacy=True)

    def test_private_backup_retains_data_and_metadata_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root/'source'
            source.mkdir(mode=0o700)
            value = source/'policy'
            value.write_bytes(b'preserved\x00bytes')
            value.chmod(0o640)
            mod.copy_private_tree(source, root/'backup')
            copy = root/'backup'/'policy'
            self.assertEqual(copy.read_bytes(), value.read_bytes())
            self.assertEqual((copy.stat().st_uid, copy.stat().st_gid, copy.stat().st_mode & 0o777),
                             (value.stat().st_uid, value.stat().st_gid, value.stat().st_mode & 0o777))
            (source/'link').symlink_to(value)
            with self.assertRaisesRegex(RuntimeError, 'unsupported backup entry'):
                mod.copy_private_tree(source, root/'rejected')

    def test_install_normalizes_source_root_and_descendants(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'src'
            root.mkdir(mode=0o777)
            root.chmod(0o777)
            (root/'module.py').write_text('x')
            (root/'module.py').chmod(0o666)
            with patch.object(mod.os, 'chown'):
                mod.normalize_installed_code(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o755)
            self.assertEqual((root/'module.py').stat().st_mode & 0o777, 0o644)

    def test_legacy_configuration_requires_exact_original_units_and_rules(self):
        dns, fw, nft = mod.legacy_files('192.168.44.10', 'eth0',
                                        '192.168.44.0/24', '1.1.1.1', 53, False)
        opts = mod.parse_legacy_files(dns, fw, nft, False)
        self.assertEqual(opts, ('192.168.44.10', 'eth0', '192.168.44.0/24', '1.1.1.1', 53))
        with self.assertRaisesRegex(RuntimeError, 'legacy'):
            mod.parse_legacy_files(dns, fw, nft + 'add table inet foreign\n', False)
        with self.assertRaisesRegex(RuntimeError, 'legacy'):
            mod.parse_legacy_files(dns + 'ExecStartPost=/bin/true\n', fw, nft, False)

    def test_private_client_scope_and_firewall(self):
        opts = mod.parse_options('192.168.44.10', 'enp1s0',
                                 '192.168.44.0/24', '9.9.9.9', 53)
        text = mod.firewall_rules(*opts[:3])
        for line in ('create table inet aleph_dns',
                     'comment "skt-aleph-dns-v1:',
                     'udp dport 53', 'tcp dport 53',
                     'iifname "enp1s0" ip saddr != 192.168.44.0/24 drop',
                     'iifname != "lo" iifname != "enp1s0" drop'):
            self.assertIn(line, text)
        self.assertNotIn('flush ruleset', text)

    def test_hardened_systemd_and_config(self):
        dns, firewall = mod.unit_files('192.168.44.10', '1.1.1.1', 53, '192.168.44.0/24')
        for line in ('User=aleph-dns', 'StateDirectoryMode=0700',
                     'AmbientCapabilities=CAP_NET_BIND_SERVICE',
                     'NoNewPrivileges=yes',
                     'ExecStartPre=+/usr/bin/python3 /opt/aleph-dns/firewall_guard.py apply /etc/aleph-dns/firewall.json',
                     '--port 53', '--system-dns',
                     '--listen-address 192.168.44.10',
                     'Requires=aleph-dns-firewall.service',
                     'IPAddressDeny=any', 'IPAddressAllow=192.168.44.0/24',
                     'IPAddressAllow=1.1.1.1/32', 'IPAddressAllow=192.168.44.10/32'):
            self.assertIn(line, dns)
        self.assertIn('Type=oneshot', firewall)
        self.assertNotIn(' --allow-public-domains', dns)
        self.assertIn(' --allow-public-domains',
                      mod.legacy_files('192.168.44.10','eth0','192.168.44.0/24','1.1.1.1',53,True)[0])

    def test_public_or_wide_or_injected_settings_rejected(self):
        cases = [
            ('0.0.0.0','eth0','192.168.4.0/24','1.1.1.1',53),
            ('127.0.0.1','eth0','192.168.4.0/24','1.1.1.1',53),
            ('8.8.8.8','eth0','192.168.4.0/24','1.1.1.1',53),
            ('192.168.4.2','eth0','0.0.0.0/0','1.1.1.1',53),
            ('192.168.4.2','eth0','192.168.0.0/16','1.1.1.1',53),
            ('192.168.4.2','eth0;touch /tmp/x','192.168.4.0/24','1.1.1.1',53),
            ('192.168.4.2','eth0','192.168.4.2/24','1.1.1.1',53),
            ('192.168.4.2','eth0','192.168.4.0/24','192.168.4.2',53),
            ('192.168.4.2','eth0','192.168.4.0/24','224.0.0.1',53),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                mod.parse_options(*case)

    def test_apply_requires_root(self):
        with patch.object(mod.os,'geteuid',return_value=1000):
            with self.assertRaises(PermissionError):
                mod.need_root()

    def test_symlink_policy_cannot_replace_other_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d); outside=path/'outside'
            outside.write_text('DO NOT EDIT')
            link=path/'policy.json'
            link.symlink_to(outside)
            with self.assertRaises(RuntimeError):
                mod.write_atomic(link,b'{}',0o600,0,0)
            self.assertEqual(outside.read_text(),'DO NOT EDIT')



class InterfaceDiscoveryTests(unittest.TestCase):
    """Mock iproute2 output; these tests never modify an actual host."""

    @staticmethod
    def ip_record(name, ip='192.168.7.69', prefix=24):
        return {'ifname': name, 'addr_info': [
            {'family': 'inet', 'local': ip, 'prefixlen': prefix}]}

    @staticmethod
    def ip_output(*records):
        return SimpleNamespace(stdout=json.dumps(records))

    @staticmethod
    def arguments(**overrides):
        values = dict(listen_ip='192.168.7.69', interface=None, client_cidr=None,
                      upstream='9.9.9.9', upstream_port=53, policy=Path('unused'),
                      apply=False)
        values.update(overrides)
        return SimpleNamespace(**values)

    @staticmethod
    def active_record(name, ip='192.168.7.69', prefix=24, flags=None):
        return {'ifname': name, 'flags': ['UP', 'BROADCAST'] if flags is None else flags,
                'addr_info': [{'family': 'inet', 'local': ip,
                               'prefixlen': prefix, 'scope': 'global'}]}

    def test_automatic_ip_and_interface_single_nic(self):
        data = self.ip_output(self.active_record('lo', '127.0.0.1', 8, ['LOOPBACK', 'UP']),
                              self.active_record('enp3s0'),
                              self.active_record('down0', '192.168.9.8', 24, []),
                              self.active_record('wan0', '203.0.113.9'))
        with patch.object(mod.subprocess, 'run', return_value=data) as run:
            self.assertEqual(mod.discover_listener_interface(),
                             ('192.168.7.69', 'enp3s0', '192.168.7.0/24'))
        run.assert_called_once_with(['ip', '-j', '-4', 'address', 'show'],
                                    capture_output=True, text=True, timeout=5, check=True)

    def test_automatic_scope_is_capped_at_24(self):
        for prefix, scope in ((16, '192.168.7.0/24'),
                              (24, '192.168.7.0/24'),
                              (27, '192.168.7.64/27'),
                              (32, '192.168.7.69/32')):
            with self.subTest(prefix=prefix), patch.object(
                    mod.subprocess, 'run',
                    return_value=self.ip_output(self.active_record('enp3s0', prefix=prefix))):
                self.assertEqual(mod.discover_listener_interface(),
                                 ('192.168.7.69', 'enp3s0', scope))

    def test_multiple_private_candidates_require_explicit_address(self):
        data = self.ip_output(self.active_record('enp3s0'),
                              self.active_record('docker0', '172.17.0.1', 16))
        with patch.object(mod.subprocess, 'run', return_value=data):
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                mod.discover_listener_interface()
            self.assertEqual(mod.discover_listener_interface('192.168.7.69'),
                             ('enp3s0', '192.168.7.0/24'))
            self.assertEqual(mod.discover_listener_interface(None, 'enp3s0'),
                             ('192.168.7.69', 'enp3s0', '192.168.7.0/24'))

    def test_multiple_ips_on_one_nic_are_ambiguous(self):
        record = self.active_record('enp3s0')
        record['addr_info'].append({'family': 'inet', 'local': '192.168.7.70',
                                    'prefixlen': 24, 'scope': 'global'})
        with patch.object(mod.subprocess, 'run', return_value=self.ip_output(record)):
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                mod.discover_listener_interface(None, 'enp3s0')
            self.assertEqual(mod.discover_listener_interface('192.168.7.69'),
                             ('enp3s0', '192.168.7.0/24'))

    def test_no_eligible_private_ip_does_not_guess(self):
        data = self.ip_output(self.active_record('lo', '127.0.0.1', 8, ['LOOPBACK', 'UP']),
                              self.active_record('eth0', '192.168.7.69', 24, ['BROADCAST']))
        with patch.object(mod.subprocess, 'run', return_value=data):
            with self.assertRaisesRegex(RuntimeError, 'no active private'):
                mod.discover_listener_interface(None)

    def test_auto_invalid_iproute2_metadata_rejected(self):
        cases = ['{}', '{', 'null',
                 json.dumps([self.active_record('enp3s0', prefix=True)]),
                 json.dumps([self.active_record('enp3s0', ip='192.168.7.69;bad')]),
                 json.dumps([{'ifname': 'enp3s0', 'flags': 'UP', 'addr_info': []}])]
        for output in cases:
            with self.subTest(output=output[:25]), patch.object(
                    mod.subprocess, 'run', return_value=SimpleNamespace(stdout=output)):
                with self.assertRaisesRegex(RuntimeError, 'invalid iproute2 JSON'):
                    mod.discover_listener_interface(None)

    def test_auto_cli_preview_without_ip_or_interface(self):
        screen = io.StringIO()
        with (
            patch.object(mod, 'discover_listener_interface',
                         return_value=('192.168.7.69', 'enp3s0', '192.168.7.0/24')) as finder,
            patch.object(mod, 'validate_policy', return_value=SimpleNamespace(digest='test')),
            patch.object(mod, 'publish_lock', side_effect=AssertionError('no writes in preview')),
            patch.object(mod, '_install_locked', side_effect=AssertionError('no install')),
            redirect_stdout(screen)
        ):
            self.assertEqual(mod.main(['install', '--upstream', '9.9.9.9',
                                       '--policy', '/tmp/unused.json']), 0)
        finder.assert_called_once_with(None, None)
        self.assertIn('Auto-detected listen IP / interface: 192.168.7.69 / enp3s0',
                      screen.getvalue())

    def test_auto_apply_requires_approved_client_range_before_discovery(self):
        with (
            patch.object(mod, 'discover_listener_interface',
                         side_effect=AssertionError('must not discover before approval')),
            patch.object(mod, 'need_root',
                         side_effect=AssertionError('must not escalate before approval'))
        ):
            with self.assertRaisesRegex(ValueError, 'explicit --client-cidr'):
                mod.install(self.arguments(listen_ip=None, apply=True))

    def test_auto_apply_installs_exact_discovered_listener_and_scope(self):
        screen = io.StringIO()
        fd = os.open(os.devnull, os.O_RDONLY)
        with (
            patch.object(mod, 'discover_listener_interface',
                         return_value=('192.168.7.69', 'enp3s0', '192.168.7.0/24')) as finder,
            patch.object(mod, 'validate_policy', return_value=SimpleNamespace(digest='test')),
            patch.object(mod, 'need_root'),
            patch.object(mod, 'publish_lock', return_value=fd),
            patch.object(mod, '_install_locked') as installer,
            redirect_stdout(screen)
        ):
            mod.install(self.arguments(listen_ip=None, client_cidr='192.168.7.0/24',
                                       apply=True))
        finder.assert_called_once_with(None, None)
        self.assertEqual(installer.call_args.args[1:6],
                         ('192.168.7.69', 'enp3s0', '192.168.7.0/24', '9.9.9.9', 53))

    def test_unique_interface_from_private_listener(self):
        data = self.ip_output(self.ip_record('lo', '127.0.0.1', 8),
                              self.ip_record('enp3s0'),
                              self.ip_record('docker0', '172.17.0.1', 16))
        with patch.object(mod.subprocess, 'run', return_value=data) as run:
            self.assertEqual(mod.discover_listener_interface('192.168.7.69'),
                             ('enp3s0', '192.168.7.0/24'))
        run.assert_called_once_with(
            ['ip', '-j', '-4', 'address', 'show'], capture_output=True,
            text=True, timeout=5, check=True)

    def test_suggested_scope_is_never_wider_than_24(self):
        for prefix, expected in ((16, '192.168.7.0/24'),
                                 (24, '192.168.7.0/24'),
                                 (27, '192.168.7.64/27'),
                                 (32, '192.168.7.69/32')):
            with self.subTest(prefix=prefix), patch.object(
                    mod.subprocess, 'run',
                    return_value=self.ip_output(self.ip_record('eth0', prefix=prefix))):
                self.assertEqual(mod.discover_listener_interface('192.168.7.69'),
                                 ('eth0', expected))

    def test_duplicate_ip_is_ambiguous_without_interface(self):
        data = self.ip_output(self.ip_record('eth0'), self.ip_record('eth1'))
        with patch.object(mod.subprocess, 'run', return_value=data):
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                mod.discover_listener_interface('192.168.7.69')
            self.assertEqual(mod.discover_listener_interface('192.168.7.69', 'eth1'),
                             ('eth1', '192.168.7.0/24'))
            with self.assertRaisesRegex(RuntimeError, 'not assigned'):
                mod.discover_listener_interface('192.168.7.69', 'eth2')

    def test_duplicate_prefix_on_one_interface_fails_closed(self):
        item = self.ip_record('eth0')
        item['addr_info'].append({'family': 'inet', 'local': '192.168.7.69',
                                  'prefixlen': 25})
        with patch.object(mod.subprocess, 'run', return_value=self.ip_output(item)):
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                mod.discover_listener_interface('192.168.7.69')

    def test_no_matching_ip_refuses_to_guess(self):
        with patch.object(mod.subprocess, 'run',
                          return_value=self.ip_output(self.ip_record('eth0',
                                                                   '192.168.7.70'))):
            with self.assertRaisesRegex(RuntimeError, 'not assigned'):
                mod.discover_listener_interface('192.168.7.69')

    def test_invalid_listener_or_override_rejected_before_host_query(self):
        with patch.object(mod.subprocess, 'run',
                          side_effect=AssertionError('must not query iproute2')):
            for ip in ('8.8.8.8', '0.0.0.0', '192.168.7.69;malicious', '::1'):
                with self.subTest(ip=ip), self.assertRaises(ValueError):
                    mod.discover_listener_interface(ip)
            with self.assertRaisesRegex(ValueError, 'invalid interface'):
                mod.discover_listener_interface('192.168.7.69', 'eth0;malicious')

    def test_invalid_json_and_address_metadata_rejected(self):
        invalid = ['{}', '{', 'null',
                   json.dumps([{'ifname': 'eth0', 'addr_info': [
                       {'family': 'inet', 'local': '192.168.7.69',
                        'prefixlen': True}]}]),
                   json.dumps([self.ip_record('eth0;unsafe')])]
        for output in invalid:
            with self.subTest(output=output[:40]), patch.object(
                    mod.subprocess, 'run', return_value=SimpleNamespace(stdout=output)):
                with self.assertRaisesRegex(RuntimeError, 'invalid iproute2 JSON'):
                    mod.discover_listener_interface('192.168.7.69')

    def test_missing_or_failed_ip_command_does_not_choose_an_interface(self):
        for failure in (FileNotFoundError('ip missing'),
                        subprocess.TimeoutExpired('ip', 5),
                        subprocess.CalledProcessError(1, 'ip')):
            with self.subTest(failure=type(failure).__name__), patch.object(
                    mod.subprocess, 'run', side_effect=failure):
                with self.assertRaisesRegex(RuntimeError, 'iproute2'):
                    mod.discover_listener_interface('192.168.7.69')

    def test_preview_shows_suggestion_but_never_calls_installer(self):
        screen = io.StringIO()
        with patch.object(mod.subprocess, 'run',
                          return_value=self.ip_output(self.ip_record('enp5s0'))), \
             patch.object(mod, 'validate_policy',
                          return_value=SimpleNamespace(digest='test-digest')), \
             patch.object(mod, 'publish_lock',
                          side_effect=AssertionError('must not lock')), \
             patch.object(mod, '_install_locked',
                          side_effect=AssertionError('must not install')), \
             redirect_stdout(screen):
            mod.install(self.arguments())
        text = screen.getvalue()
        self.assertIn('Auto-detected interface owning listener IP: enp5s0', text)
        self.assertIn('SUGGESTED client CIDR (preview only, NOT approved): 192.168.7.0/24',
                      text)
        self.assertIn('--client-cidr 192.168.7.0/24 --apply', text)

    def test_apply_never_infers_client_authorization(self):
        with patch.object(mod, 'discover_listener_interface',
                          side_effect=AssertionError('must reject before looking at host')), \
             patch.object(mod, 'need_root',
                          side_effect=AssertionError('must reject before privilege check')), \
             patch.object(mod, 'publish_lock',
                          side_effect=AssertionError('must reject before lock')):
            with self.assertRaisesRegex(ValueError, 'explicit --client-cidr'):
                mod.install(self.arguments(apply=True))

    def test_apply_uses_discovered_nic_and_explicit_scope(self):
        screen = io.StringIO()
        descriptor = os.open(os.devnull, os.O_RDONLY)
        with patch.object(mod, 'discover_listener_interface',
                          return_value=('enp3s0', '192.168.7.0/24')) as finder, \
             patch.object(mod, 'validate_policy',
                          return_value=SimpleNamespace(digest='test-digest')), \
             patch.object(mod, 'need_root'), \
             patch.object(mod, 'publish_lock', return_value=descriptor), \
             patch.object(mod, '_install_locked') as install, \
             redirect_stdout(screen):
            mod.install(self.arguments(client_cidr='192.168.7.0/24', apply=True))
        finder.assert_called_once_with('192.168.7.69', None)
        install.assert_called_once()
        self.assertEqual(install.call_args.args[1:6],
                         ('192.168.7.69', 'enp3s0', '192.168.7.0/24', '9.9.9.9', 53))
        self.assertIn('Explicitly approved client scope: 192.168.7.0/24',
                      screen.getvalue())

    def test_explicit_interface_and_scope_keep_previous_semantics(self):
        with patch.object(mod, 'discover_listener_interface',
                          side_effect=AssertionError('do not auto-detect')), \
             patch.object(mod, 'validate_policy',
                          return_value=SimpleNamespace(digest='test-digest')):
            mod.install(self.arguments(interface='eth0', client_cidr='192.168.7.0/24'))

    def test_cli_accepts_minimal_preview_without_nic_or_scope(self):
        screen = io.StringIO()
        with patch.object(mod, 'discover_listener_interface',
                          return_value=('enp3s0', '192.168.7.0/24')), \
             patch.object(mod, 'validate_policy',
                          return_value=SimpleNamespace(digest='test-digest')), \
             redirect_stdout(screen):
            code = mod.main(['install', '--listen-ip', '192.168.7.69',
                             '--upstream', '9.9.9.9', '--policy', '/tmp/unused.json'])
        self.assertEqual(code, 0)
        self.assertIn('PREVIEW ONLY', screen.getvalue())


class InstallerLifecycleTests(unittest.TestCase):
    """Pure/mocked system management: never touch a real systemd or nftables service."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for attr, location in (
            ('ETC', root/'etc'),
            ('STATE_DIR', root/'state'),
            ('UNIT_DIR', root/'units'),
            ('CODE', root/'opt'/'aleph-dns'/'src'),
            ('BACKUP_DIR', root/'backup'),
            ('LOCK_PATH', root/'aleph.lock'),
            ('MIGRATION_JOURNAL', root/'migration.json'),
        ):
            p = patch.object(mod, attr, location)
            p.start()
            self.addCleanup(p.stop)
        mod.ETC.mkdir()
        mod.UNIT_DIR.mkdir()
        mod.STATE_DIR.mkdir()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        (mod.ETC/'options.json').write_text(json.dumps({
            'managed_by': mod.OWNERSHIP_MARKER
        }))
        (mod.ETC/'options.json').chmod(0o600)
        self.account = SimpleNamespace(pw_gid=os.getgid())
        # Tests simulate distinct installations in temporary code directories.
        # A cached dns_agent.__path__ must never survive deletion of that directory.
        self.addCleanup(self._clear_dns_modules)

    @staticmethod
    def _clear_dns_modules():
        for name in list(sys.modules):
            if name == 'dns_agent' or name.startswith('dns_agent.'):
                sys.modules.pop(name, None)

    def owned_resources(self):
        owned = {}
        for path in (mod.ETC, mod.CODE.parent, mod.STATE_DIR,
                     mod.UNIT_DIR/'aleph-dns.service', mod.UNIT_DIR/'aleph-dns-firewall.service'):
            if path.exists():
                owned[path] = (mod.identity(path), path.read_bytes() if path.is_file() else None)
        for base in (mod.ETC, mod.CODE.parent):
            if base.is_dir():
                for item in base.rglob('*'):
                    owned[item] = (mod.identity(item), item.read_bytes() if item.is_file() else None)
        return owned

    def normalize_fixture_code(self):
        with patch.object(mod.os, 'chown'):
            mod.normalize_installed_code(mod.CODE)

    def policy(self, issued_delta=0, expired=False):
        issued = self.now+timedelta(seconds=issued_delta)
        expires = self.now+timedelta(hours=-1 if expired else 1)
        if expired:
            issued = self.now-timedelta(hours=3)
        elif issued >= expires:
            expires = issued+timedelta(hours=1)
        return {'issued_at': issued.isoformat(),
                'expires_at': expires.isoformat(), 'rules': []}

    def prepare_published(self, previous, incoming):
        (mod.ETC/'policy.json').write_text(json.dumps(previous))
        source = mod.ETC/'candidate.json'
        source.write_text(json.dumps(incoming))
        (mod.STATE_DIR/'state.json').write_text(json.dumps({'policy': json.dumps(previous)}))
        mod.CODE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(mod.ROOT/'apps'/'dns-agent'/'src', mod.CODE, dirs_exist_ok=True)
        self.normalize_fixture_code()
        (mod.ETC/'installed-code.json').write_text(
            json.dumps({'managed_by': mod.OWNERSHIP_MARKER,
                        'contents': mod.installed_code_inventory()}))
        (mod.ETC/'installed-code.json').chmod(0o600)
        return SimpleNamespace(policy=source)

    def test_nft_table_collision_detection_uses_json_ownership_scope(self):
        obj={'nftables':[{'metainfo': {'version':'1.0'}},
                         {'table': {'family':'inet','name':'aleph_dns'}}]}
        with patch.object(mod.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(obj))):
            self.assertTrue(mod.table_exists())
        obj['nftables'][1]['table']['name']='other_table'
        with patch.object(mod.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(obj))):
            self.assertFalse(mod.table_exists())
        with patch.object(mod.subprocess, 'run', return_value=SimpleNamespace(stdout='invalid')):
            with self.assertRaises(RuntimeError): mod.table_exists()

    def test_publish_rejects_missing_marker(self):
        (mod.ETC/'options.json').write_text('{"allow_public_domains":false}')
        with self.assertRaisesRegex(RuntimeError, 'verified ALEPH'):
            mod.read_options()

    def test_old_mode_requires_verified_upgrade(self):
        p = mod.ETC/'options.json'
        p.write_text(json.dumps({'managed_by':mod.OWNERSHIP_MARKER,
                                 'allow_public_domains':False}))
        with self.assertRaisesRegex(RuntimeError, 'upgrade --apply'):
            mod.read_options()
        self.assertFalse(mod.read_options(allow_historical=True)['allow_public_domains'])
        p.write_text(json.dumps({'managed_by':mod.OWNERSHIP_MARKER,
                                 'allow_public_domains':'false'}))
        with self.assertRaisesRegex(RuntimeError, 'unrecognized'):
            mod.read_options(allow_historical=True)

    def test_public_domain_policy_is_valid_with_no_extra_mode(self):
        policy = self.policy()
        policy['rules'] = [{'domain':'reviewed.example.org', 'decision':'BLOCK',
                            'scope':'SUBTREE', 'approved':True,
                            'expires_at':policy['expires_at'], 'evidence':'test-approved'}]
        candidate = mod.ETC/'candidate.json'
        candidate.write_text(json.dumps(policy))
        parsed = mod.validate_policy(candidate)
        self.assertEqual(parsed.blocked(self.now), ('reviewed.example.org',))

    def test_publish_rejects_stale_and_equal_issuance_conflict(self):
        incoming=self.policy(issued_delta=-120)
        current=self.policy(issued_delta=-60)
        args=self.prepare_published(current, incoming)
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod, 'write_atomic') as write:
            with self.assertRaisesRegex(RuntimeError, 'stale or conflicting'):
                mod.publish(args)
            write.assert_not_called()
        incoming=self.policy(issued_delta=-60)
        incoming['expires_at']=(self.now+timedelta(minutes=30)).isoformat()
        args=self.prepare_published(current, incoming)
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod, 'write_atomic') as write:
            with self.assertRaisesRegex(RuntimeError, 'stale or conflicting'):
                mod.publish(args)
            write.assert_not_called()

    def test_publish_accepts_newer_policy_after_previous_expiry(self):
        args=self.prepare_published(self.policy(expired=True), self.policy(issued_delta=-1))
        recorded=[]
        def atomic(path,data,mode,owner,group):
            recorded.append((str(path), data))
            path.write_bytes(data)
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod.pwd, 'getpwnam', return_value=self.account), \
             patch.object(mod, 'write_atomic', side_effect=atomic), \
             patch.object(mod, 'await_published_policy') as acknowledge:
            mod.publish(args)
            self.assertEqual(len(recorded), 1)
            self.assertIn(b'"issued_at"', (mod.ETC/'policy.json').read_bytes())
            acknowledge.assert_called_once()

    def test_publish_must_not_claim_success_without_acknowledgement(self):
        args=self.prepare_published(self.policy(issued_delta=-60), self.policy(issued_delta=-1))
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod.pwd, 'getpwnam', return_value=self.account), \
             patch.object(mod, 'write_atomic', side_effect=lambda p,d,m,o,g:p.write_bytes(d)), \
             patch.object(mod, 'await_published_policy', side_effect=RuntimeError('timeout')):
            with self.assertRaisesRegex(RuntimeError, 'timeout'):
                mod.publish(args)

    def test_publish_refuses_recovery_in_progress(self):
        args=self.prepare_published(self.policy(issued_delta=-60), self.policy(issued_delta=-1))
        (mod.STATE_DIR/'pending.json').write_text('{}')
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod, 'write_atomic') as write:
            with self.assertRaisesRegex(RuntimeError,'pending DNS recovery'):
                mod.publish(args)
            write.assert_not_called()

    def test_install_cleanup_removes_only_dedicated_resources(self):
        foreign=(mod.UNIT_DIR/'unrelated.service')
        foreign.write_text('KEEP')
        for n in ('aleph-dns.service','aleph-dns-firewall.service'):
            (mod.UNIT_DIR/n).write_text('owned service')
        mod.CODE.parent.mkdir(parents=True)
        mod.CODE.mkdir(mode=0o755)
        (mod.CODE/'agent.py').write_text('dummy')
        (mod.ETC/'firewall.json').write_text('{}')
        with patch.object(mod, 'firewall_guard') as guard, \
             patch.object(mod, 'service_active', return_value=False), \
             patch.object(mod.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='')) as run:
            mod.cleanup_failed_install(owned=self.owned_resources(), remove_service_account=False, remove_state=True)
            self.assertFalse(mod.ETC.exists())
            self.assertFalse(mod.CODE.parent.exists())
            self.assertFalse(mod.STATE_DIR.exists())
            self.assertFalse((mod.UNIT_DIR/'aleph-dns.service').exists())
            self.assertEqual(foreign.read_text(), 'KEEP')
            self.assertEqual([c.args[0] for c in guard.call_args_list], ['check', 'remove'])

    def test_rollback_preserves_evidence_if_firewall_is_foreign(self):
        (mod.ETC/'firewall.json').write_text('{}')
        (mod.UNIT_DIR/'aleph-dns.service').write_text('owned')
        with patch.object(mod, 'firewall_guard', side_effect=RuntimeError('ownership mismatch')), \
             patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'ownership mismatch'):
                mod.cleanup_failed_install(owned=self.owned_resources())
            run.assert_not_called()
        self.assertTrue((mod.ETC/'firewall.json').exists())
        self.assertTrue((mod.UNIT_DIR/'aleph-dns.service').exists())

    def test_uninstall_legacy_install_preserves_services_and_state(self):
        with patch.object(mod, 'need_root'), \
             patch.object(mod, 'inspect_existing', return_value={'legacy': True}), \
             patch.object(mod, 'migrate_existing') as migrate, \
             patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'adopt-legacy-table'):
                mod.uninstall(SimpleNamespace(apply=True))
            migrate.assert_not_called()
            run.assert_not_called()
        self.assertTrue(mod.ETC.exists())
        self.assertTrue(mod.STATE_DIR.exists())

    def test_legacy_upgrade_without_operator_adoption_does_not_stop_services(self):
        with patch.object(mod, 'need_root'), \
             patch.object(mod, 'inspect_existing', return_value={'legacy': True}), \
             patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'adopt-legacy-table'):
                mod.upgrade(SimpleNamespace(apply=True, adopt_legacy_table=False))
            run.assert_not_called()

    def test_upgrade_rejects_incompatible_service_python_before_migration(self):
        with patch.object(mod, 'need_root'), \
             patch.object(mod, 'inspect_existing', return_value={'legacy': False}), \
             patch.object(mod.subprocess, 'run', return_value=SimpleNamespace(returncode=1)), \
             patch.object(mod, 'migrate_existing') as migrate:
            with self.assertRaisesRegex(RuntimeError, 'service Python'):
                mod.upgrade(SimpleNamespace(apply=True, adopt_legacy_table=False))
            migrate.assert_not_called()


    def test_unowned_directory_blocks_all_rollback(self):
        (mod.UNIT_DIR/'aleph-dns.service').write_text('service')
        owned = self.owned_resources()
        owned.pop(mod.ETC)
        with patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'unowned or replaced'):
                mod.cleanup_failed_install(owned=owned)
            run.assert_not_called()
        self.assertTrue(mod.ETC.exists())
        self.assertTrue((mod.UNIT_DIR/'aleph-dns.service').exists())

    def test_changed_unit_blocks_all_rollback(self):
        unit = mod.UNIT_DIR/'aleph-dns.service'
        unit.write_text('original')
        owned = self.owned_resources()
        unit.write_text('changed')
        with patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'modified install resource'):
                mod.cleanup_failed_install(owned=owned)
            run.assert_not_called()
        self.assertEqual(unit.read_text(), 'changed')

    def test_new_unit_never_overwrites_concurrent_creation(self):
        unit = mod.UNIT_DIR/'aleph-dns.service'
        unit.write_text('foreign')
        owned = {}
        with self.assertRaises(FileExistsError):
            mod.write_new(unit, b'ours', 0o644, os.getuid(), os.getgid(), owned)
        self.assertEqual(unit.read_text(), 'foreign')
        self.assertEqual(owned, {})


    def test_rollback_refuses_untracked_static_configuration(self):
        owned = self.owned_resources()
        foreign = mod.ETC/'created-by-other-admin'
        foreign.write_text('PRESERVE')
        with patch.object(mod.subprocess, 'run') as invoke:
            with self.assertRaisesRegex(RuntimeError, 'unowned nested'):
                mod.cleanup_failed_install(owned=owned)
            invoke.assert_not_called()
        self.assertEqual(foreign.read_text(), 'PRESERVE')
        self.assertTrue(mod.ETC.is_dir())

    def test_rollback_refuses_untracked_code_in_root_owned_directory(self):
        mod.CODE.parent.mkdir(parents=True)
        mod.CODE.mkdir(mode=0o755)
        (mod.CODE/'agent.py').write_text('expected')
        owned = self.owned_resources()
        foreign = mod.CODE/'foreign.py'
        foreign.write_text('PRESERVE')
        with patch.object(mod.subprocess, 'run') as invoke:
            with self.assertRaisesRegex(RuntimeError, 'unowned nested'):
                mod.cleanup_failed_install(owned=owned)
            invoke.assert_not_called()
        self.assertEqual(foreign.read_text(), 'PRESERVE')

    def test_rollback_refuses_unknown_service_state(self):
        owned = self.owned_resources()
        foreign = mod.STATE_DIR/'new-service-artifact.bin'
        foreign.write_text('PRESERVE')
        with patch.object(mod.subprocess, 'run') as invoke:
            with self.assertRaisesRegex(RuntimeError, 'unexpected state content'):
                mod.cleanup_failed_install(owned=owned)
            invoke.assert_not_called()
        self.assertEqual(foreign.read_text(), 'PRESERVE')

    def test_manifest_detects_added_and_modified_code(self):
        mod.CODE.parent.mkdir(parents=True)
        mod.CODE.mkdir(mode=0o755)
        code = mod.CODE/'agent.py'
        code.write_text('original')
        self.normalize_fixture_code()
        manifest = {'managed_by': mod.OWNERSHIP_MARKER,
                    'contents': mod.installed_code_inventory()}
        (mod.ETC/'installed-code.json').write_text(json.dumps(manifest))
        (mod.ETC/'installed-code.json').chmod(0o600)
        mod.verify_installed_code()
        code.write_text('altered')
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            mod.verify_installed_code()
        code.write_text('original')
        (mod.CODE/'unrecognized').write_text('PRESERVE')
        (mod.CODE/'unrecognized').chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'differs'):
            mod.verify_installed_code()

    def test_publish_refuses_unverified_installed_code_before_mutation(self):
        args = self.prepare_published(self.policy(issued_delta=-60),
                                      self.policy(issued_delta=-1))
        (mod.CODE/'unexpected.py').write_text('not in manifest')
        (mod.CODE/'unexpected.py').chmod(0o644)
        with patch.object(mod, 'need_root'), patch.object(mod.subprocess, 'run') as invoke, \
             patch.object(mod, 'write_atomic') as atomic:
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                mod.publish(args)
            invoke.assert_not_called()
            atomic.assert_not_called()

    def test_uninstall_checks_source_before_stopping_service(self):
        with patch.object(mod, 'need_root'), \
             patch.object(mod, 'inspect_existing', side_effect=RuntimeError('code differs')), \
             patch.object(mod, 'migrate_existing') as migrate, \
             patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                mod.uninstall(SimpleNamespace(apply=True))
            migrate.assert_not_called()
            run.assert_not_called()

    def test_uninstall_checks_backup_destination_before_service_stop(self):
        outside = Path(self.temp.name)/'outside'
        outside.mkdir()
        mod.BACKUP_DIR.symlink_to(outside)
        existing = {'legacy': True, 'options': ('192.168.44.10', 'eth0', '192.168.44.0/24', '1.1.1.1', 53)}
        with patch.object(mod, 'migration_snapshot'), patch.object(mod.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'backup directory symlink'):
                mod.migrate_existing(existing, 'uninstall')
            run.assert_not_called()
        self.assertTrue(mod.ETC.exists())

    def test_privileged_import_disables_bytecode_in_working_tree(self):
        self.assertTrue(mod.sys.dont_write_bytecode)

    def test_uninstall_preview_has_no_side_effect(self):
        args=SimpleNamespace(apply=False)
        with patch.object(mod, 'need_root') as root, patch.object(mod.subprocess, 'run') as run:
            mod.uninstall(args)
            root.assert_not_called()
            run.assert_not_called()

    def test_lifecycle_lock_rejects_symlink_and_writable_file(self):
        outside = mod.LOCK_PATH.parent/'outside'
        outside.write_text('preserve')
        mod.LOCK_PATH.symlink_to(outside)
        with self.assertRaises(OSError):
            mod.publish_lock()
        self.assertEqual(outside.read_text(), 'preserve')
        mod.LOCK_PATH.unlink()
        os.mkfifo(mod.LOCK_PATH)
        with self.assertRaisesRegex(RuntimeError, 'unsafe lifecycle lock'):
            mod.publish_lock()
        mod.LOCK_PATH.unlink()
        mod.LOCK_PATH.write_text('lock')
        mod.LOCK_PATH.chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'unsafe lifecycle lock'):
            mod.publish_lock()

    def test_lifecycle_lock_rejects_non_root_owner_when_root(self):
        fake_stat = SimpleNamespace(st_mode=0o100600, st_uid=1000)
        with patch.object(mod.os, 'geteuid', return_value=0), \
             patch.object(mod.os, 'fstat', return_value=fake_stat):
            with self.assertRaisesRegex(RuntimeError, 'root-owned'):
                mod.publish_lock()

    def test_legacy_publish_lock_is_held_exclusively(self):
        fd = mod.legacy_publish_lock()
        try:
            with self.assertRaises(BlockingIOError):
                mod.legacy_publish_lock()
        finally:
            os.close(fd)

    def test_install_apply_refuses_while_lifecycle_lock_is_held(self):
        args = SimpleNamespace(listen_ip='192.168.44.10', interface='eth0',
                               client_cidr='192.168.44.0/24', upstream='1.1.1.1',
                               upstream_port=53, policy=Path('unused'),
                               apply=True)
        fd = mod.publish_lock()
        try:
            with patch.object(mod, 'need_root'), \
                 patch.object(mod, 'validate_policy', return_value=SimpleNamespace(digest='fixture')), \
                 patch.object(mod, '_install_locked') as install:
                with self.assertRaises(BlockingIOError):
                    mod.install(args)
                install.assert_not_called()
        finally:
            os.close(fd)

    def test_install_preview_does_not_create_lock(self):
        args = SimpleNamespace(listen_ip='192.168.44.10', interface='eth0',
                               client_cidr='192.168.44.0/24', upstream='1.1.1.1',
                               upstream_port=53, policy=Path('unused'),
                               apply=False)
        with patch.object(mod, 'validate_policy', return_value=SimpleNamespace(digest='fixture')):
            mod.install(args)
        self.assertFalse(mod.LOCK_PATH.exists())

    def test_uninstall_refuses_while_publication_lock_is_held(self):
        fd = mod.publish_lock()
        try:
            with patch.object(mod, 'need_root'), patch.object(mod.subprocess, 'run') as run:
                with self.assertRaises(BlockingIOError):
                    mod.uninstall(SimpleNamespace(apply=True))
                run.assert_not_called()
            self.assertTrue(mod.ETC.exists())
        finally:
            os.close(fd)

    def test_publish_refuses_while_uninstall_lock_is_held(self):
        fd = mod.publish_lock()
        try:
            with patch.object(mod, 'need_root'), patch.object(mod, 'write_atomic') as write:
                with self.assertRaises(BlockingIOError):
                    mod.publish(SimpleNamespace(policy=mod.ETC/'policy.json'))
                write.assert_not_called()
        finally:
            os.close(fd)

    def test_uninstall_routes_to_the_backup_transaction(self):
        existing = {'legacy': False}
        with patch.object(mod, 'need_root'), \
             patch.object(mod, 'inspect_existing', return_value=existing), \
             patch.object(mod, 'migrate_existing') as migrate:
            mod.uninstall(SimpleNamespace(apply=True))
            migrate.assert_called_once_with(existing, 'uninstall')


    def test_running_newer_state_prevents_publishing_intermediate_policy(self):
        old=self.policy(issued_delta=-180)
        candidate=self.policy(issued_delta=-60)
        state_newer=self.policy(issued_delta=-30)
        args=self.prepare_published(old, candidate)
        (mod.STATE_DIR/'state.json').write_text(json.dumps({'policy': json.dumps(state_newer)}))
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod, 'write_atomic') as write:
            with self.assertRaisesRegex(RuntimeError,'stale or conflicting'):
                mod.publish(args)
            write.assert_not_called()

    def test_idempotent_publish_requires_acknowledgement(self):
        previous=self.policy(issued_delta=-10)
        args=self.prepare_published(previous, previous)
        with patch.object(mod, 'need_root'), patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod, 'await_published_policy') as ack, \
             patch.object(mod, 'write_atomic') as write:
            mod.publish(args)
            ack.assert_called_once()
            write.assert_not_called()

    def test_rollback_stop_failure_does_not_delete_live_service_sources(self):
        (mod.UNIT_DIR/'aleph-dns.service').write_text('managed')
        mod.CODE.parent.mkdir(parents=True)
        mod.CODE.mkdir(mode=0o755)
        def failed_stop(cmd, **kwargs):
            if cmd[:3]==['systemctl','disable','--now']:
                return SimpleNamespace(returncode=1,stderr='stop refused')
            return SimpleNamespace(returncode=0,stderr='')
        with patch.object(mod, 'service_active', return_value=True), \
             patch.object(mod.subprocess, 'run', side_effect=failed_stop), \
             patch.object(mod, 'table_exists', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'could not be stopped'):
                mod.cleanup_failed_install(owned=self.owned_resources())
        self.assertTrue(mod.ETC.exists())
        self.assertTrue(mod.CODE.parent.exists())

    def test_uninstall_rejects_unrecognized_service_units(self):
        with patch.object(mod, 'need_root'), \
             patch.object(mod, 'inspect_existing', side_effect=RuntimeError('unexpected systemd unit')), \
             patch.object(mod, 'migrate_existing') as migrate:
            with self.assertRaisesRegex(RuntimeError, 'unexpected systemd unit'):
                mod.uninstall(SimpleNamespace(apply=True))
            migrate.assert_not_called()

    def test_service_acknowledgement_rejects_wrong_policy_sha(self):
        (mod.STATE_DIR/'state.json').write_text('{"policy_sha256":"other-sha"}')
        with patch.object(mod, 'service_active', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'live DNS did not confirm'):
                mod.await_published_policy('expected-sha', seconds=.05)

    def test_publish_acknowledgement_checks_live_dns(self):
        import importlib
        sys.path.insert(0, str(mod.ROOT/'apps'/'dns-agent'/'src'))
        importlib.import_module('dns_agent.runtime')
        config = 'port=53\nlisten-address=192.168.44.10\nhost-record=health-test.capstone.test,192.0.2.1,2001:db8::1\n'
        (mod.STATE_DIR/'state.json').write_text(json.dumps({'policy_sha256':'known-sha','config':config}))
        sys.path.insert(0, str(mod.ROOT/'apps'/'dns-agent'/'src'))
        with patch.object(mod, 'service_active', return_value=True),              patch('dns_agent.runtime.dns_rcode', return_value=0) as query:
            mod.await_published_policy('known-sha', seconds=0.25)
            query.assert_called_once()
        with patch.object(mod, 'service_active', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'inactive'):
                mod.await_published_policy('nope', seconds=.25)

    def test_live_health_probe_rejects_wrong_response(self):
        import importlib
        sys.path.insert(0, str(mod.ROOT/'apps'/'dns-agent'/'src'))
        importlib.import_module('dns_agent.runtime')
        state={'config':'port=53\nlisten-address=192.168.44.10\nhost-record=health-test.capstone.test,192.0.2.1,2001:db8::1\n'}
        with patch('dns_agent.runtime.dns_rcode', return_value=3):
            with self.assertRaisesRegex(RuntimeError, 'invalid answer'):
                mod.verify_running_dns(state)
        with patch('dns_agent.runtime.dns_rcode', return_value=0):
            mod.verify_running_dns(state)
        with self.assertRaises(RuntimeError):
            mod.verify_running_dns({'config':'port=53\nlisten-address=0.0.0.0\n'})

    def test_installed_parser_requires_real_installed_source(self):
        (mod.ETC/'policy.json').write_text(json.dumps(self.policy()))
        with self.assertRaisesRegex(RuntimeError, 'missing or not root-owned'):
            mod.validate_policy(mod.ETC/'policy.json', installed=True)

if __name__ == '__main__':
    unittest.main()
