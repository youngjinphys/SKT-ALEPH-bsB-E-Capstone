"""Tests for the service's additional map-free cgroup IP guard."""
import importlib.util
import ipaddress
import socket
import subprocess
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / 'apps/dns-agent/src/dns_agent/cgroup_guard.py'
spec = importlib.util.spec_from_file_location('aleph_cgroup_guard', MODULE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def run_bytecode(program, packet, protocol):
    """Execute the emitted instruction subset against a synthetic skb."""
    instructions = list(struct.iter_unpack('=BBhi', program))
    registers = [0] * 11
    registers[1], registers[10] = 0x10000, 128
    stack = bytearray(128)
    pc = 0
    while pc < len(instructions):
        op, regs, offset, immediate = instructions[pc]
        dst, src = regs & 15, regs >> 4
        pc += 1
        if op == 0xbf:
            registers[dst] = registers[src]
        elif op == 0xb7:
            registers[dst] = immediate & 0xffffffffffffffff
        elif op == 0x07:
            registers[dst] = (registers[dst] + immediate) & 0xffffffffffffffff
        elif op == 0x61:
            registers[dst] = (socket.htons(protocol) if registers[src] == 0x10000 and offset == 16
                              else struct.unpack_from('=I', stack, registers[src] + offset)[0])
        elif op == 0x71:
            registers[dst] = stack[registers[src] + offset]
        elif op == 0x54:
            registers[dst] = (registers[dst] & 0xffffffff) & (immediate & 0xffffffff)
        elif op == 0xdc:
            registers[dst] = socket.htonl(registers[dst] & 0xffffffff)
        elif op == 0x85:
            if len(packet) < registers[4]:
                registers[0] = (-14) & 0xffffffffffffffff
            else:
                start = registers[3]
                stack[start:start+registers[4]] = packet[:registers[4]]
                registers[0] = 0
        elif op == 0x55:
            if registers[dst] != (immediate & 0xffffffffffffffff): pc += offset
        elif op == 0x16:
            if (registers[dst] & 0xffffffff) == (immediate & 0xffffffff): pc += offset
        elif op == 0x95:
            return registers[0]
        else:
            raise AssertionError(f'unexpected instruction {op:#x}')
    raise AssertionError('program did not exit')


def ipv4_packet(source, destination):
    return (b'\x45' + bytes(11) + ipaddress.IPv4Address(source).packed +
            ipaddress.IPv4Address(destination).packed)


class ProgramTests(unittest.TestCase):
    def test_parent_allow_must_not_expand_configured_filter(self):
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        guard.validate_parent_allow('', networks)
        guard.validate_parent_allow('127.0.0.0/8 192.168.7.69/32', networks)
        for value in ('10.1.0.0/16', '::1/128', 'not-an-ip'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                guard.validate_parent_allow(value, networks)

    def test_parent_allow_query_rejects_failure_and_expansion(self):
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        with patch.object(guard.subprocess, 'run', side_effect=[Mock(stdout=''), Mock(stdout='')]) as query:
            guard.check_parent_allows(networks)
            self.assertEqual(query.call_count, 2)
        with patch.object(guard.subprocess, 'run', side_effect=subprocess.TimeoutExpired('systemctl', 10)):
            with self.assertRaisesRegex(RuntimeError, 'cannot inspect'):
                guard.check_parent_allows(networks)
        with patch.object(guard.subprocess, 'run', return_value=Mock(stdout='10.0.0.0/8')):
            with self.assertRaisesRegex(RuntimeError, 'exceeds'):
                guard.check_parent_allows(networks)
    def test_real_emitted_instructions_enforce_source_and_destination(self):
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        ingress = guard.compile_program(networks, ingress=True)
        egress = guard.compile_program(networks, ingress=False)
        for address, expected in [('127.4.3.2', 1), ('192.168.7.69', 1),
                                  ('192.168.7.200', 1), ('8.8.8.8', 1),
                                  ('192.168.8.1', 0), ('1.1.1.1', 0)]:
            with self.subTest(address=address):
                self.assertEqual(run_bytecode(ingress, ipv4_packet(address, '1.1.1.1'), 0x0800), expected)
                self.assertEqual(run_bytecode(egress, ipv4_packet('1.1.1.1', address), 0x0800), expected)
        self.assertEqual(run_bytecode(ingress, b'\x45', 0x0800), 0)
        self.assertEqual(run_bytecode(egress, bytes(40), 0x86dd), 0)

    def test_only_the_managed_service_cgroup_is_accepted(self):
        self.assertEqual(guard.service_cgroup('0::/system.slice/aleph-dns.service\n'),
                         '/system.slice/aleph-dns.service')
        for raw in ('0::/system.slice/other.service\n', '0::/\n',
                    '0::/system.slice/aleph-dns.service/child\n', ''):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                guard.service_cgroup(raw)

    def test_exact_configured_prefixes_are_retained(self):
        actual = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        self.assertEqual(set(actual), {ipaddress.ip_network('127.0.0.0/8'),
                                      ipaddress.ip_network('192.168.7.0/24'),
                                      ipaddress.ip_network('192.168.7.69/32'),
                                      ipaddress.ip_network('8.8.8.8/32')})

    def test_rejects_unsafe_or_noncanonical_addresses(self):
        for listen, subnet, upstream in [('0.0.0.0', '192.168.7.0/24', '8.8.8.8'),
                                          ('192.168.7.69', '0.0.0.0/0', '8.8.8.8'),
                                          ('192.168.7.69', '192.168.7.1/24', '8.8.8.8'),
                                          ('192.168.7.69', '192.168.7.0/24', '224.0.0.1')]:
            with self.subTest(listen=listen, subnet=subnet, upstream=upstream):
                with self.assertRaises(ValueError):
                    guard.allowed_networks(listen, subnet, upstream)

    def test_programs_are_nonempty_and_differ_by_direction(self):
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        ingress = guard.compile_program(networks, ingress=True)
        egress = guard.compile_program(networks, ingress=False)
        self.assertEqual(len(ingress) % 8, 0)
        self.assertGreater(len(ingress), 0)
        self.assertNotEqual(ingress, egress)
        self.assertEqual(struct.unpack('=BBhi', ingress[-8:])[0], 0x95)
        self.assertEqual(struct.unpack('=BBhi', egress[-8:])[0], 0x95)

    def test_failed_second_hook_rolls_back_only_own_first_hook(self):
        backend = Mock(unsafe=True)
        backend.load.side_effect = [31, 32]
        backend.program_id.side_effect = [101, 102]
        backend.query.side_effect = [[101, 9], [101, 9], []]
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        with self.assertRaisesRegex(RuntimeError, 'attachment'):
            guard.install(backend, 20, networks)
        self.assertEqual(backend.detach.call_count, 2)
        self.assertEqual([c.args for c in backend.detach.call_args_list], [(20, 32, 1), (20, 31, 0)])
        self.assertEqual([c.args for c in backend.close.call_args_list], [(32,), (31,)])

    def test_success_preserves_preexisting_programs(self):
        backend = Mock(unsafe=True)
        backend.load.side_effect = [31, 32]
        backend.program_id.side_effect = [101, 102]
        backend.query.side_effect = [[9, 101], [9, 101], [10, 102], [10, 102]]
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        guard.install(backend, 20, networks)
        backend.detach.assert_not_called()
        self.assertEqual([c.args for c in backend.attach.call_args_list], [(20, 31, 0), (20, 32, 1)])

    def test_stale_owned_program_aborts_before_modification(self):
        backend = Mock(unsafe=True)
        backend.assert_no_stale.side_effect = RuntimeError('stale program')
        backend.query.return_value = []
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            guard.install(backend, 20, networks)
        backend.load.assert_not_called()
        backend.attach.assert_not_called()

    def test_preflight_load_failure_closes_first_program_without_attaching(self):
        backend = Mock()
        backend.load.side_effect = [31, OSError('load failed')]
        networks = guard.allowed_networks('192.168.7.69', '192.168.7.0/24', '8.8.8.8')
        with self.assertRaisesRegex(OSError, 'load failed'):
            guard.preflight(backend, networks)
        backend.close.assert_called_once_with(31)
        backend.attach.assert_not_called()

    def test_short_kernel_program_info_is_rejected(self):
        backend = object.__new__(guard.KernelBackend)
        backend.call = Mock(return_value=(0, struct.pack('=IIQ', 31, 4, 0)))
        with self.assertRaisesRegex(RuntimeError, 'short BPF program info'):
            backend.program_id(31)

    def test_short_existing_program_name_is_not_treated_as_empty(self):
        backend = object.__new__(guard.KernelBackend)
        backend.query = Mock(return_value=[101])
        backend.call = Mock(side_effect=[(31, b''), (0, struct.pack('=IIQ', 31, 79, 0))])
        with patch.object(guard.os, 'close') as close:
            with self.assertRaisesRegex(RuntimeError, 'short BPF program info'):
                backend.assert_no_stale(20, 0)
        close.assert_called_once_with(31)


if __name__ == '__main__':
    unittest.main()
