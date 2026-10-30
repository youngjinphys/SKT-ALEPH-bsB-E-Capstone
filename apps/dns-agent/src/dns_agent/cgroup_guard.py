"""Construct and attach a map-free service cgroup IP filter."""
import ipaddress
import ctypes
import os
import platform
import socket
import struct
import subprocess
import sys
from pathlib import Path

PRIVATE = tuple(map(ipaddress.ip_network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))

def service_cgroup(raw):
    entries = [line[3:] for line in raw.splitlines() if line.startswith('0::')]
    if entries != ['/system.slice/aleph-dns.service']:
        raise RuntimeError('refusing to modify an unexpected service cgroup')
    return entries[0]

def validate_parent_allow(value, networks):
    if len(value) > 65536:
        raise RuntimeError('parent slice IP allow list is too large')
    collapsed = tuple(ipaddress.collapse_addresses(networks))
    for token in value.split():
        try:
            prefix = ipaddress.ip_network(token, strict=False)
        except ValueError as exc:
            raise RuntimeError('cannot parse parent slice IP allow list') from exc
        if prefix.version != 4 or not any(prefix.subnet_of(allowed) for allowed in collapsed):
            raise RuntimeError('parent slice IP allow list exceeds the managed DNS guard')


def check_parent_allows(networks):
    for unit in ('system.slice', '-.slice'):
        try:
            result = subprocess.run(['systemctl', 'show', '--value', '--property=IPAddressAllow',
                                     '--', unit], capture_output=True, text=True,
                                    timeout=10, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError('cannot inspect parent slice IP allow list') from exc
        validate_parent_allow(result.stdout, networks)

def allowed_networks(listen, subnet, upstream):
    local = ipaddress.IPv4Address(listen)
    clients = ipaddress.IPv4Network(subnet, strict=True)
    remote = ipaddress.IPv4Address(upstream)
    if (not any(local in net for net in PRIVATE) or
            not any(clients.subnet_of(net) for net in PRIVATE) or clients.prefixlen < 24 or
            remote.is_multicast or remote.is_unspecified):
        raise ValueError('invalid managed DNS IP configuration')
    return (ipaddress.IPv4Network('127.0.0.0/8'),
            ipaddress.IPv4Network(f'{local}/32'), clients,
            ipaddress.IPv4Network(f'{remote}/32'))

def compile_program(networks, *, ingress):
    def ins(code, dst=0, src=0, off=0, imm=0):
        if imm > 0x7fffffff:
            imm -= 1 << 32
        return [code, dst | (src << 4), off, imm]

    # cgroup skb packet data begins at the network header. Inspect a complete
    # IPv4 header, then compare source (ingress) or destination (egress).
    code = [ins(0xbf, 6, 1), ins(0x61, 7, 6, 16),
            ins(0x55, 7, imm=socket.htons(0x0800)),
            ins(0xb7, 2, imm=0), ins(0xbf, 3, 10), ins(0x07, 3, imm=-32),
            ins(0xb7, 4, imm=20), ins(0x85, imm=26), ins(0x55, 0, imm=0),
            ins(0x71, 2, 10, -32), ins(0x54, 2, imm=0xf0),
            ins(0x55, 2, imm=0x40), ins(0x61, 2, 10, -32 + (12 if ingress else 16)),
            ins(0xdc, 2, imm=32)]
    denies = [2, 8, 11]
    matches = []
    for network in networks:
        code.extend((ins(0xbf, 3, 2), ins(0x54, 3, imm=int(network.netmask)),
                     ins(0x16, 3, imm=int(network.network_address))))
        matches.append(len(code)-1)
    deny = len(code)
    code.extend((ins(0xb7, 0, imm=0), ins(0x95)))
    allow = len(code)
    code.extend((ins(0xb7, 0, imm=1), ins(0x95)))
    for index in denies:
        code[index][2] = deny - index - 1
    for index in matches:
        code[index][2] = allow - index - 1
    return b''.join(struct.pack('=BBhi', *instruction) for instruction in code)

def install(backend, cgroup_fd, networks):
    opened = []
    attached = []
    try:
        for hook in (0, 1):
            backend.assert_no_stale(cgroup_fd, hook)
        for hook, ingress in ((0, True), (1, False)):
            fd = backend.load(compile_program(networks, ingress=ingress), hook)
            opened.append(fd)
            program_id = backend.program_id(fd)
            backend.attach(cgroup_fd, fd, hook)
            attached.append((fd, hook))
            if (program_id not in backend.query(cgroup_fd, hook) or
                    program_id not in backend.query(cgroup_fd, hook, effective=True)):
                raise RuntimeError('cgroup BPF attachment verification failed')
    except BaseException as exc:
        errors = []
        for fd, hook in reversed(attached):
            try:
                backend.detach(cgroup_fd, fd, hook)
            except OSError as cleanup:
                errors.append(str(cleanup))
        if errors:
            raise RuntimeError('BPF attachment rollback failed: ' + '; '.join(errors)) from exc
        raise
    finally:
        for fd in reversed(opened):
            backend.close(fd)


def preflight(backend, networks):
    opened = []
    try:
        for hook, ingress in ((0, True), (1, False)):
            opened.append(backend.load(compile_program(networks, ingress=ingress), hook))
    finally:
        for fd in reversed(opened):
            backend.close(fd)


class KernelBackend:
    """Linux bpf(2), using MULTI attachment so other programs are untouched."""
    def __init__(self):
        machine = platform.machine().lower()
        if machine in ('x86_64', 'amd64'):
            self.number = 321
        elif machine in ('aarch64', 'arm64'):
            self.number = 280
        elif machine.startswith('armv'):
            self.number = 386
        else:
            raise RuntimeError(f'unsupported BPF syscall architecture: {machine}')
        self.libc = ctypes.CDLL(None, use_errno=True)

    def call(self, command, data):
        attr = ctypes.create_string_buffer(data, len(data))
        ctypes.set_errno(0)
        result = self.libc.syscall(ctypes.c_long(self.number), ctypes.c_long(command),
                                   ctypes.byref(attr), ctypes.c_uint(len(data)))
        if result < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return result, attr.raw

    def load(self, instructions, hook):
        program = ctypes.create_string_buffer(instructions, len(instructions))
        license_data = ctypes.create_string_buffer(b'GPL')
        log = ctypes.create_string_buffer(65536)
        name = b'aleph_ingress' if hook == 0 else b'aleph_egress'
        attr = struct.pack('=IIQQIIQII16sII', 8, len(instructions)//8,
                           ctypes.addressof(program), ctypes.addressof(license_data),
                           1, len(log), ctypes.addressof(log), 0, 0, name, 0, hook)
        try:
            return self.call(5, attr)[0]
        except OSError as exc:
            raise RuntimeError('BPF program load failed: ' + log.value.decode(errors='replace')[-2000:]) from exc

    def program_info(self, fd, minimum):
        info = ctypes.create_string_buffer(256)
        _, attr = self.call(15, struct.pack('=IIQ', fd, len(info), ctypes.addressof(info)))
        if struct.unpack_from('=I', attr, 4)[0] < minimum:
            raise RuntimeError('short BPF program info')
        return info.raw

    def program_id(self, fd):
        value = struct.unpack_from('=I', self.program_info(fd, 8), 4)[0]
        if not value:
            raise RuntimeError('kernel did not return a BPF program ID')
        return value

    def assert_no_stale(self, cgroup_fd, hook):
        for program_id in self.query(cgroup_fd, hook):
            fd = self.call(13, struct.pack('=III', program_id, 0, 0))[0]
            try:
                info = self.program_info(fd, 80)
                if struct.unpack_from('=I', info, 4)[0] != program_id:
                    raise RuntimeError('cgroup BPF program changed during inspection')
                name = info[64:80].split(b'\0', 1)[0]
                if name in (b'aleph_ingress', b'aleph_egress'):
                    raise RuntimeError('stale ALEPH cgroup BPF program; preserve for inspection')
            finally:
                os.close(fd)

    def attach(self, cgroup_fd, fd, hook):
        self.call(8, struct.pack('=IIIII', cgroup_fd, fd, hook, 2, 0))

    def detach(self, cgroup_fd, fd, hook):
        self.call(9, struct.pack('=IIIII', cgroup_fd, fd, hook, 0, 0))

    def query(self, cgroup_fd, hook, *, effective=False):
        ids = (ctypes.c_uint32 * 512)()
        attr = struct.pack('=IIIIQIIQ', cgroup_fd, hook, int(effective), 0,
                           ctypes.addressof(ids), len(ids), 0, 0)
        _, result = self.call(16, attr)
        count = struct.unpack_from('=I', result, 24)[0]
        if count > len(ids):
            raise RuntimeError('too many cgroup BPF programs to verify')
        return list(ids[:count])

    def close(self, fd):
        os.close(fd)


def open_service_cgroup():
    service_cgroup(Path('/proc/self/cgroup').read_text())
    mounts = [line.split(' - ', 1) for line in Path('/proc/self/mountinfo').read_text().splitlines()
              if ' - ' in line]
    roots = [left.split() for left, right in mounts
             if right.split()[0] == 'cgroup2' and len(left.split()) >= 5
             and left.split()[4] == '/sys/fs/cgroup']
    if len(roots) != 1 or roots[0][3] != '/':
        raise RuntimeError('expected an unshifted unified cgroup2 mount')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    root = os.open('/sys/fs/cgroup', flags)
    try:
        parent = os.open('system.slice', flags, dir_fd=root)
        try:
            return os.open('aleph-dns.service', flags, dir_fd=parent)
        finally:
            os.close(parent)
    finally:
        os.close(root)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if os.geteuid() != 0 or len(args) != 3:
            raise RuntimeError('root and listener, client CIDR, upstream are required')
        networks = allowed_networks(*args)
        check_parent_allows(networks)
        fd = open_service_cgroup()
        try:
            install(KernelBackend(), fd, networks)
        finally:
            os.close(fd)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: cgroup IP guard: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
