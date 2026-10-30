#!/usr/bin/env python3
"""Install a dedicated LAN DNS service on Linux; no router or host resolver edits.

Default 'install' is read-only. The --apply gate authorizes root-owned files,
a dedicated systemd service and an isolated nftables input ACL.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
from datetime import datetime, timezone
import grp
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True  # No root-owned __pycache__ in source or /opt.

ROOT = Path(__file__).resolve().parents[2]
ETC = Path('/etc/aleph-dns')
CODE = Path('/opt/aleph-dns/src')
UNIT_DIR = Path('/etc/systemd/system')
STATE_DIR = Path('/var/lib/aleph-dns')
BACKUP_DIR = Path('/var/backups')
LOCK_PATH = Path('/run/aleph-dns.lock')
MIGRATION_JOURNAL = Path('/var/lib/aleph-dns-migration.json')
OWNERSHIP_MARKER = 'skt-aleph-managed-dns'
USER = 'aleph-dns'
PRIVATE = tuple(ipaddress.ip_network(x) for x in
                ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
IFNAME = re.compile(r'[A-Za-z0-9_.:-]{1,15}\Z')


_guard_spec = importlib.util.spec_from_file_location('aleph_firewall_guard', Path(__file__).with_name('firewall_guard.py'))
_guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(_guard)

def parse_options(listen, interface, subnet, upstream, upstream_port):
    try:
        ip = ipaddress.IPv4Address(listen)
        cidr = ipaddress.IPv4Network(subnet, strict=True)
        remote = ipaddress.IPv4Address(upstream)
    except ValueError as exc:
        raise ValueError('IPv4 listener, canonical client CIDR and IPv4 upstream required') from exc
    if (not any(ip in n for n in PRIVATE)
            or not any(cidr.subnet_of(n) for n in PRIVATE)):
        raise ValueError('private RFC1918 listener and client subnet required')
    if cidr.prefixlen < 24:
        raise ValueError('client scope must be /24 or narrower')
    if not IFNAME.fullmatch(interface):
        raise ValueError('invalid interface name')
    if type(upstream_port) is not int or not 1 <= upstream_port <= 65535 or remote.is_multicast or remote.is_unspecified:
        raise ValueError('invalid upstream')
    if remote == ip and upstream_port == 53:
        raise ValueError('upstream DNS loop detected')
    return str(ip), interface, str(cidr), str(remote), upstream_port


def firewall_rules(listen, interface, subnet, token='0' * 32):
    return _guard.render({'listen': listen, 'interface': interface,
                          'subnet': subnet, 'token': token})


def firewall_guard(action):
    subprocess.run(['/usr/bin/python3', str(CODE.parent/'firewall_guard.py'), action,
                    str(ETC/'firewall.json')], timeout=15, check=True)


def check_rollback_firewall():
    if (ETC/'firewall.json').exists():
        firewall_guard('check')
    elif table_exists():
        raise RuntimeError('cannot prove firewall ownership during rollback; preserve installation for inspection')


def unit_files(listen, upstream, upstream_port, client_cidr, *, cgroup_guard=True):
    dns = f"""[Unit]
Description=ALEPH Managed Protective DNS (private LAN IPv4)
Wants=network-online.target
Requires=aleph-dns-firewall.service
After=network-online.target aleph-dns-firewall.service

[Service]
Type=simple
User=aleph-dns
Group=aleph-dns
WorkingDirectory=/opt/aleph-dns
Environment=PYTHONPATH=/opt/aleph-dns/src
StateDirectory=aleph-dns
StateDirectoryMode=0700
ExecStartPre=+/usr/bin/python3 /opt/aleph-dns/firewall_guard.py apply /etc/aleph-dns/firewall.json
ExecStart=/usr/bin/python3 -m dns_agent run /etc/aleph-dns/policy.json --port 53 --system-dns --listen-address {listen} --upstream {upstream} --upstream-port {upstream_port} --state-dir /var/lib/aleph-dns
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
ProtectKernelModules=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
IPAddressDeny=any
IPAddressAllow=127.0.0.0/8
IPAddressAllow={listen}/32
IPAddressAllow={client_cidr}
IPAddressAllow={upstream}/32
Restart=on-failure
RestartSec=3s
TimeoutStopSec=7s

[Install]
WantedBy=multi-user.target
"""
    if cgroup_guard:
        marker = 'ExecStart=/usr/bin/python3 -m dns_agent run '
        dns = dns.replace(marker, f'ExecStartPre=+/usr/bin/python3 -B -m dns_agent.cgroup_guard {listen} {client_cidr} {upstream}\n' + marker)
    fw = """[Unit]
Description=ALEPH DNS scoped ingress filter
After=local-fs.target nftables.service
Before=aleph-dns.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 /opt/aleph-dns/firewall_guard.py apply /etc/aleph-dns/firewall.json
ExecReload=/usr/bin/python3 /opt/aleph-dns/firewall_guard.py apply /etc/aleph-dns/firewall.json

[Install]
WantedBy=multi-user.target
"""
    return dns, fw


def legacy_files(listen, interface, subnet, upstream, upstream_port, allow_public):
    dns, fw = unit_files(listen, upstream, upstream_port, subnet, cgroup_guard=False)
    # Historical migration compatibility only. New units never write this flag.
    if allow_public:
        dns = dns.replace(' --state-dir /var/lib/aleph-dns\n',
                          ' --state-dir /var/lib/aleph-dns --allow-public-domains\n')
    dns = dns.replace('ExecStartPre=+/usr/bin/python3 /opt/aleph-dns/firewall_guard.py apply /etc/aleph-dns/firewall.json',
                      'ExecStartPre=+/usr/sbin/nft -f /etc/aleph-dns/firewall.nft')
    dns = dns.replace('RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK',
                      'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6')
    fw = fw.replace('/usr/bin/python3 /opt/aleph-dns/firewall_guard.py apply /etc/aleph-dns/firewall.json',
                    '/usr/sbin/nft -f /etc/aleph-dns/firewall.nft')
    lines = ['add table inet aleph_dns',
             'add chain inet aleph_dns input { type filter hook input priority -100; policy accept; }',
             'flush chain inet aleph_dns input']
    for proto in ('udp', 'tcp'):
        target = f'ip daddr {listen} {proto} dport 53'
        lines.append(f'add rule inet aleph_dns input {target} iifname != "lo" iifname != "{interface}" drop')
        lines.append(f'add rule inet aleph_dns input {target} iifname "{interface}" ip saddr != {subnet} drop')
    return dns, fw, '\n'.join(lines) + '\n'


def parse_legacy_files(dns, fw, nft, allow_public):
    match = re.search(r'^ExecStart=/usr/bin/python3 -m dns_agent run /etc/aleph-dns/policy.json --port 53 --system-dns --listen-address (\S+) --upstream (\S+) --upstream-port (\d+) --state-dir /var/lib/aleph-dns(?: --allow-public-domains)?$', dns, re.MULTILINE)
    rule = re.search(r'^add rule inet aleph_dns input ip daddr (\S+) udp dport 53 iifname "([^"]+)" ip saddr != (\S+) drop$', nft, re.MULTILINE)
    if not match or not rule:
        raise RuntimeError('unrecognized legacy configuration')
    listen, upstream, port = match.groups()
    rule_listen, interface, subnet = rule.groups()
    try:
        opts = parse_options(listen, interface, subnet, upstream, int(port))
    except (ValueError, TypeError) as exc:
        raise RuntimeError('invalid legacy configuration') from exc
    if rule_listen != listen or (dns, fw, nft) != legacy_files(*opts, allow_public):
        raise RuntimeError('legacy configuration differs from the original installation')
    return opts


def inspect_interface(listen, interface):
    result = subprocess.run(['ip', '-j', '-4', 'address', 'show', 'dev', interface],
                            capture_output=True, text=True, timeout=5, check=True)
    assigned = {record.get('local') for item in json.loads(result.stdout)
                for record in item.get('addr_info', [])}
    if listen not in assigned:
        raise RuntimeError(f'LAN IP {listen} is not assigned to interface {interface}')


def discover_listener_interface(listen=None, preferred=None):
    """Resolve a LAN binding; infer IP only when one safe candidate exists.

    Explicit --listen-ip retains the previous behavior. Without it, consider
    UP non-loopback interfaces with globally scoped RFC1918 IPv4 addresses.
    Never silently choose among multiple addresses, VPNs or container bridges.
    """
    explicit = listen is not None
    if explicit:
        try:
            address = ipaddress.IPv4Address(listen)
        except (ValueError, TypeError) as exc:
            raise ValueError('listener must be an IPv4 address') from exc
        if not any(address in network for network in PRIVATE):
            raise ValueError('listener must be a private RFC1918 IPv4 address')
    if preferred is not None and (not isinstance(preferred, str)
                                  or not IFNAME.fullmatch(preferred)):
        raise ValueError('invalid interface name')
    try:
        result = subprocess.run(
            ['ip', '-j', '-4', 'address', 'show'], capture_output=True,
            text=True, timeout=5, check=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('cannot inspect host IPv4 interfaces; install/check iproute2') from exc
    try:
        interfaces = json.loads(result.stdout)
        if not isinstance(interfaces, list):
            raise ValueError('expected interface list')
        matches = set()
        for device in interfaces:
            if not isinstance(device, dict):
                raise ValueError('invalid interface record')
            name, entries = device.get('ifname'), device.get('addr_info')
            if not isinstance(entries, list):
                raise ValueError('missing IPv4 address list')
            if not explicit:
                flags = device.get('flags')
                if (not isinstance(name, str) or not IFNAME.fullmatch(name)
                        or not isinstance(flags, list)
                        or any(not isinstance(flag, str) for flag in flags)):
                    raise ValueError('invalid interface metadata')
                if (name == 'lo' or 'LOOPBACK' in flags or 'UP' not in flags):
                    continue
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError('invalid address record')
                if entry.get('family') != 'inet':
                    continue
                if explicit:
                    if entry.get('local') != str(address):
                        continue
                    candidate = address
                else:
                    if entry.get('scope', 'global') != 'global':
                        continue
                    try:
                        candidate = ipaddress.IPv4Address(entry.get('local'))
                    except (ValueError, TypeError) as exc:
                        raise ValueError('invalid address literal') from exc
                    if not any(candidate in network for network in PRIVATE):
                        continue
                prefix = entry.get('prefixlen')
                if (not isinstance(name, str) or not IFNAME.fullmatch(name)
                        or type(prefix) is not int or not 1 <= prefix <= 32):
                    raise ValueError('invalid matching interface or IPv4 prefix')
                if preferred is None or name == preferred:
                    matches.add((str(candidate), name, prefix))
    except (ValueError, TypeError) as exc:
        raise RuntimeError('invalid iproute2 JSON; cannot infer a safe listener') from exc
    if not matches:
        if explicit:
            suffix = f' on --interface {preferred}' if preferred else ''
            raise RuntimeError(f'listener IP {address} is not assigned{suffix}')
        raise RuntimeError('no active private IPv4 listener; inspect ip -4 -br addr or specify --listen-ip')
    if len(matches) != 1:
        raise RuntimeError('ambiguous private IPv4 listeners; specify --listen-ip (and optionally --interface)')
    chosen, interface, prefix = matches.pop()
    suggested = ipaddress.IPv4Network((chosen, max(24, prefix)), strict=False)
    return (interface, str(suggested)) if explicit else (chosen, interface, str(suggested))


def check_free_port(listen):
    for kind in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
        with socket.socket(socket.AF_INET, kind) as sock:
            sock.bind((listen, 53))


def check_service_python():
    """Validate the interpreter used by systemd, not only the invoking Python."""
    try:
        result = subprocess.run(
            ['/usr/bin/python3', '-I', '-c',
             'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('unable to execute service Python /usr/bin/python3') from exc
    if result.returncode != 0:
        raise RuntimeError('service Python /usr/bin/python3 must be 3.11 or newer')


def check_parent_ip_allows(listen, subnet, upstream):
    sys.path.insert(0, str(ROOT/'apps'/'dns-agent'/'src'))
    from dns_agent.cgroup_guard import KernelBackend, allowed_networks, check_parent_allows, preflight
    networks = allowed_networks(listen, subnet, upstream)
    check_parent_allows(networks)
    preflight(KernelBackend(), networks)


def validate_policy(path, *, installed=False, allow_expired=False):
    # Policy publication must be parsed by the same root-managed code running
    # under systemd, not by a potentially newer or user-writable checkout.
    source = CODE if installed else ROOT/'apps'/'dns-agent'/'src'
    if installed:
        if (source.is_symlink() or not source.is_dir() or
                (os.geteuid() == 0 and source.stat().st_uid != 0)):
            raise RuntimeError('installed DNS parser is missing or not root-owned')
    sys.path.insert(0, str(source))
    from dns_agent.policy import parse_policy
    from dns_agent.transaction import read_regular
    policy = parse_policy(read_regular(path))
    if not allow_expired and policy.expires_at <= datetime.now(timezone.utc):
        raise ValueError('policy already expired; generate a new policy')
    return policy


def write_atomic(path, data, mode, owner, group):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RuntimeError(f'unsafe destination path: {path}')
    fd, temp = tempfile.mkstemp(prefix='.aleph-stage-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, owner, group)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_owned_atomic(path, data, mode, owner, group, owned):
    """Record each committed installer file immediately to support partial rollback."""
    write_atomic(path, data, mode, owner, group)
    owned[path] = (identity(path), data)


def identity(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino)


def write_new(path, data, mode, owner, group, owned):
    """Create a file exclusively and remember its identity before writing."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        info = os.fstat(fd)
        owned[path] = ((info.st_dev, info.st_ino), data)
        os.fchmod(fd, mode)
        os.fchown(fd, owner, group)
        with os.fdopen(fd, 'wb') as stream:
            fd = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd != -1:
            os.close(fd)


def record_directory(path, owned):
    owned[path] = (identity(path), None)



def root_group_exclusive():
    try:
        if any(entry.pw_gid == 0 and entry.pw_uid != 0 for entry in pwd.getpwall()):
            return False
        return all(pwd.getpwnam(name).pw_uid == 0 for name in grp.getgrgid(0).gr_mem)
    except (KeyError, OSError):
        return False


def historical_source_permissions(path, info):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or
            stat.S_IMODE(info.st_mode) != 0o775):
        return False
    try:
        attrs = os.listxattr(path, follow_symlinks=False)
        return root_group_exclusive() and not ({'system.posix_acl_access',
                                                'system.posix_acl_default'} & set(attrs))
    except OSError:
        return False


def installed_code_inventory(base=None, *, allow_historical_src=False):
    base = CODE.parent if base is None else Path(base)
    if base.is_symlink() or not base.is_dir():
        raise RuntimeError('installed code directory missing or replaced')
    result = {}
    for item in sorted(base.rglob('*')):
        st = item.lstat()
        legacy_writable = False
        if allow_historical_src and item == base/'src':
            legacy_writable = historical_source_permissions(item, st)
        if (stat.S_ISLNK(st.st_mode) or
                (os.geteuid() == 0 and st.st_uid != 0) or (st.st_mode & 0o022 and not legacy_writable)):
            raise RuntimeError(f'unsafe installed code entry: {item}')
        name = item.relative_to(base).as_posix()
        if stat.S_ISDIR(st.st_mode):
            result[name] = {'kind': 'dir'}
        elif stat.S_ISREG(st.st_mode):
            with item.open('rb') as inp:
                result[name] = {'kind': 'file', 'sha256': hashlib.file_digest(inp, 'sha256').hexdigest()}
        else:
            raise RuntimeError(f'unsupported installed code entry: {item}')
    return result


def normalize_installed_code(root):
    for item in (root, *root.rglob('*')):
        os.chown(item, 0, 0)
        item.chmod(0o755 if item.is_dir() else 0o644)


def verify_historical_code(*, legacy):
    hashes = {
        '__init__.py': {'f74222e09e410d49a2fcd46ac0233182c03497320d38f2de0f221d4e31760504'},
        '__main__.py': {'50e572361caf4ff6a34f1b2463c9cb288d8ca55110173d862813c8853dfdaf20',
                        '98c707c7d0f2a8348454f1bcc23922f954f9eca1c4c7b66771338b23cbfa3e3e'},
        '_child.py': {'f43119103916f76fba247b67a3a394ce7b94934e156ca620011ef3335a881cac'},
        'policy.py': {'7ece95cfd1e3a323d8a9585594d6fc39b0f98f4e104e280e694e85904f57b0f6'},
        'runtime.py': {'75f912f09cf3fa5baaf53910ea9249ecc78b37b93eadf6151431e51ca468ac34'},
        'transaction.py': {'19b69a3f9796d77e7f4983e7a5b718094f66db24ddc3a88cc8cef2fb45ddb119'},
    }
    inventory = installed_code_inventory(allow_historical_src=True)
    names = {'src', 'src/dns_agent'} | {'src/dns_agent/'+name for name in hashes}
    if not legacy:
        names.add('firewall_guard.py')
    extra = set(inventory) - names
    cache = 'src/dns_agent/__pycache__'
    if cache in extra and inventory[cache] == {'kind': 'dir'}:
        extra.remove(cache)
        for name in tuple(extra):
            match = re.fullmatch(r'src/dns_agent/__pycache__/([A-Za-z_]+)\.cpython-[0-9]+(?:\.opt-[12])?\.pyc', name)
            if match and match.group(1)+'.py' in hashes and inventory[name].get('kind') == 'file':
                extra.remove(name)
    if not names.issubset(inventory) or extra:
        raise RuntimeError('historical code inventory differs; preserve for inspection')
    if any(inventory['src/dns_agent/'+name].get('sha256') not in allowed
           for name, allowed in hashes.items()):
        raise RuntimeError('historical code content differs; preserve for inspection')
    if not legacy and inventory['firewall_guard.py'].get('sha256') != '05bc796f9d92f30b97becca41d3a350d89f17535de8944b643ccff8a3ce97b9a':
        raise RuntimeError('historical firewall guard differs; preserve for inspection')


def verify_installed_code():
    # Do NOT import installed code before its integrity has been checked.
    path = ETC/'installed-code.json'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or
                (os.geteuid() == 0 and info.st_uid != 0) or
                info.st_mode & 0o022):
            raise RuntimeError('unsafe installed manifest')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(1024*1024 + 1)
        if len(raw) > 1024*1024:
            raise RuntimeError('installed manifest exceeds 1 MiB')
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError('installed code manifest invalid') from exc
    finally:
        os.close(fd)
    if (not isinstance(data, dict) or set(data) != {'managed_by', 'contents'}
            or data['managed_by'] != OWNERSHIP_MARKER
            or not isinstance(data['contents'], dict)
            or data['contents'] != installed_code_inventory()):
        raise RuntimeError('installed code differs from installation manifest; preserve for inspection')


def remember_static(directory, owned):
    for item in directory.rglob('*'):
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise RuntimeError(f'unsafe static install resource: {item}')
        owned[item] = (identity(item), item.read_bytes() if item.is_file() else None)


def check_rollback_state():
    if not STATE_DIR.exists():
        return
    allowed = {'lock', 'active.conf', 'state.json', 'pending.json', 'candidate.conf'}
    for item in STATE_DIR.iterdir():
        if (item.is_symlink() or not item.is_file() or
                (item.name not in allowed
                 and not re.fullmatch(r'\.candidate-[A-Za-z0-9_-]+', item.name))):
            raise RuntimeError(f'unexpected state content; preserve for inspection: {item}')

def verify_install_ownership(owned):
    required = (ETC, CODE.parent, STATE_DIR, UNIT_DIR/'aleph-dns.service',
                UNIT_DIR/'aleph-dns-firewall.service')
    for directory in (ETC, CODE.parent):
        if directory.exists() and not directory.is_symlink():
            for item in directory.rglob('*'):
                if item not in owned:
                    raise RuntimeError(f'unowned nested install resource; preserve for inspection: {item}')
    check_rollback_state()
    for path in set(required) | set(owned):
        try:
            actual = identity(path)
        except FileNotFoundError:
            continue
        expected = owned.get(path)
        if expected is None or actual != expected[0] or path.is_symlink():
            raise RuntimeError(f'unowned or replaced install resource; preserve for inspection: {path}')
        if expected[1] is not None and path.read_bytes() != expected[1]:
            raise RuntimeError(f'modified install resource; preserve for inspection: {path}')


def need_root():
    if os.geteuid() != 0:
        raise PermissionError('system installation and policy publication require sudo')



def table_exists() -> bool:
    """Fail closed if the reserved nft table belongs to another configuration."""
    result = subprocess.run(['/usr/sbin/nft', '-j', 'list', 'tables'],
                            capture_output=True, text=True, timeout=8, check=True)
    try:
        entries = json.loads(result.stdout)['nftables']
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('cannot inspect nftables ownership') from exc
    return any(entry.get('table', {}).get('family') == 'inet'
               and entry['table'].get('name') == 'aleph_dns'
               for entry in entries if isinstance(entry, dict))


def service_active() -> bool:
    return subprocess.run(['systemctl', 'is-active', '--quiet', 'aleph-dns.service'],
                          timeout=5, check=False).returncode == 0


def await_installed_dns(policy, *, listen, upstream, upstream_port, seconds=12):
    """Confirm our exact local health owner and installed policy, not merely a PID."""
    sys.path.insert(0, str(ROOT/'apps'/'dns-agent'/'src'))
    from dns_agent.policy import render_config
    from dns_agent.runtime import dns_rcode
    rendered = render_config(policy.blocked(datetime.now(timezone.utc)),
                             port=53, upstream=upstream, upstream_port=upstream_port,
                             listen_address=listen, system_dns=True)
    health = next(line.split('=', 1)[1].split(',')[0]
                  for line in rendered.splitlines() if line.startswith('host-record='))
    canaries = policy.blocked(datetime.now(timezone.utc))
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if service_active():
            try:
                for qtype, literal in ((1, '192.0.2.1'), (28, '2001:db8::1')):
                    expected = socket.inet_pton(socket.AF_INET if qtype == 1
                                                else socket.AF_INET6, literal)
                    dns_rcode(health, qtype, 53, server_ip=listen,
                              require_answer=True, expected_rdata=expected)
                if canaries:
                    if dns_rcode(canaries[0], 1, 53, server_ip=listen) != 3:
                        raise RuntimeError('blocked domain not intercepted')
                raw = (STATE_DIR/'state.json').read_bytes()
                state = json.loads(raw)
                if state.get('policy_sha256') != policy.digest:
                    raise RuntimeError('running agent has not accepted the requested policy')
                firewall_guard('verify')
                return
            except (OSError, RuntimeError, ValueError):
                pass
        time.sleep(.2)
    raise RuntimeError('systemd/DNS policy acknowledgement timed out; refusing to claim success')


def cleanup_failed_install(*, owned, remove_service_account=False, remove_state=False):
    """Best-effort rollback of only resources whose absence was checked before install."""
    verify_install_ownership(owned)
    check_rollback_firewall()
    errors = []
    names = ('aleph-dns.service', 'aleph-dns-firewall.service')
    for name in names:
        if not (UNIT_DIR/name).exists():
            continue
        try:
            result = subprocess.run(['systemctl', 'disable', '--now', name],
                                    capture_output=True, text=True, timeout=15, check=False)
            if result.returncode:
                errors.append(f'could not stop {name}: {result.stderr[-400:]}')
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f'could not stop {name}: {exc}')
    # Never delete code or credentials while the owned service may still be running.
    if errors or service_active():
        raise RuntimeError('installation services could not be stopped: ' + '; '.join(errors))
    try:
        if (ETC/'firewall.json').exists():
            firewall_guard('remove')
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f'cannot remove verified firewall; preserve installation: {exc}') from exc
    for name in names:
        try:
            (UNIT_DIR/name).unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f'cannot remove unit {name}: {exc}')
    for directory in (CODE.parent, ETC):
        try:
            if directory.exists():
                shutil.rmtree(directory)
        except OSError as exc:
            errors.append(f'cannot remove {directory}: {exc}')
    try:
        subprocess.run(['systemctl', 'daemon-reload'],
                       capture_output=True, text=True, timeout=15, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f'daemon-reload: {exc}')
    if remove_state:
        try:
            if STATE_DIR.exists():
                shutil.rmtree(STATE_DIR)
        except OSError as exc:
            errors.append(f'state directory cleanup: {exc}')
    if remove_service_account:
        try:
            subprocess.run(['userdel', USER], capture_output=True, text=True,
                           timeout=10, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f'account cleanup: {exc}')
    if errors:
        raise RuntimeError('installation rollback incomplete: ' + '; '.join(errors))


def read_options(*, allow_historical=False):
    path = ETC/'options.json'
    options = json.loads(protected_text(path, forbidden=0o077))
    if not isinstance(options, dict) or options.get('managed_by') != OWNERSHIP_MARKER:
        raise RuntimeError('not a verified ALEPH installation; manual inspection required')
    if set(options) == {'managed_by'}:
        return options
    # Previous managed installations may contain a retired domain-mode flag.
    # Recognize it only for backed-up upgrade/removal, never for live publishing.
    if (set(options) == {'managed_by', 'allow_public_domains'}
            and type(options['allow_public_domains']) is bool):
        if allow_historical:
            return options
        raise RuntimeError('legacy domain-mode installation; run upgrade --apply before publishing')
    raise RuntimeError('unrecognized installation options; manual inspection required')


def protected_text(path, *, forbidden=0o022, owner=0):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & forbidden or
                (os.geteuid() == 0 and info.st_uid != owner)):
            raise RuntimeError(f'unsafe installation file: {path}')
        with os.fdopen(os.dup(fd), 'r', encoding='utf-8') as stream:
            data = stream.read(4*1024*1024 + 1)
        if len(data) > 4*1024*1024:
            raise RuntimeError(f'installation file exceeds size limit: {path}')
        return data
    finally:
        os.close(fd)


def inspect_existing():
    options = read_options(allow_historical=True)
    for path in (ETC, CODE.parent, STATE_DIR):
        st = path.lstat()
        if (not stat.S_ISDIR(st.st_mode) or st.st_mode & (0o077 if path == STATE_DIR else 0o022) or
                (os.geteuid() == 0 and st.st_uid != (pwd.getpwnam(USER).pw_uid if path == STATE_DIR else 0))):
            raise RuntimeError(f'unsafe installation directory: {path}')
    dns_path = UNIT_DIR/'aleph-dns.service'
    fw_path = UNIT_DIR/'aleph-dns-firewall.service'
    dns, fw = protected_text(dns_path), protected_text(fw_path)
    for path in (dns_path, fw_path):
        result = subprocess.run(['systemctl', 'show', path.name,
                                 '--property=FragmentPath', '--property=DropInPaths'],
                                capture_output=True, text=True, timeout=10, check=True)
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if fields.get('FragmentPath') != str(path) or fields.get('DropInPaths') != '':
            raise RuntimeError(f'unexpected loaded unit or drop-ins: {path.name}')
    historical = not (ETC/'installed-code.json').exists()
    if not historical:
        verify_installed_code()
    else:
        verify_historical_code(legacy=not (ETC/'firewall.json').exists())
    inventory = installed_code_inventory(allow_historical_src=historical)
    if not (ETC/'firewall.json').exists():
        opts = parse_legacy_files(dns, fw, protected_text(ETC/'firewall.nft'),
                                  options.get('allow_public_domains', False))
        return {'legacy': True, 'options': opts,
                'inventory': inventory, 'historical': historical}
    config = json.loads(protected_text(ETC/'firewall.json', forbidden=0o077))
    _guard.validate_config(config)
    match = re.search(r'^ExecStart=/usr/bin/python3 -m dns_agent run /etc/aleph-dns/policy.json --port 53 --system-dns --listen-address (\S+) --upstream (\S+) --upstream-port (\d+) --state-dir /var/lib/aleph-dns(?: --allow-public-domains)?$', dns, re.MULTILINE)
    if not match:
        raise RuntimeError('unrecognized managed DNS unit')
    listen, upstream, port = match.groups()
    opts = parse_options(listen, config['interface'], config['subnet'], upstream, int(port))
    guard = protected_text(CODE.parent/'firewall_guard.py').encode()
    trusted_guards = {'05bc796f9d92f30b97becca41d3a350d89f17535de8944b643ccff8a3ce97b9a',
                      hashlib.sha256(Path(__file__).with_name('firewall_guard.py').read_bytes()).hexdigest()}
    expected_dns, expected_fw = unit_files(listen, upstream, int(port), config['subnet'])
    prior_dns, prior_fw = unit_files(listen, upstream, int(port), config['subnet'], cgroup_guard=False)
    if options.get('allow_public_domains', False):
        # Verify the exact historic unit before migrating; do not run the old switch.
        expected_dns = expected_dns.replace(' --state-dir /var/lib/aleph-dns\n',
                                            ' --state-dir /var/lib/aleph-dns --allow-public-domains\n')
        prior_dns = prior_dns.replace(' --state-dir /var/lib/aleph-dns\n',
                                      ' --state-dir /var/lib/aleph-dns --allow-public-domains\n')
    if (listen != config['listen'] or (dns, fw) not in ((expected_dns, expected_fw), (prior_dns, prior_fw)) or
            hashlib.sha256(guard).hexdigest() not in trusted_guards):
        raise RuntimeError('managed unit or guard differs; preserve for inspection')
    return {'legacy': False, 'options': opts, 'config': config,
            'inventory': inventory, 'historical': historical}


def publish_lock(*, allow_migration=False):
    # This lock must outlive the configuration directory, including uninstall
    # and a subsequent reinstall; locking inside ETC would permit an inode swap.
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or
                (os.geteuid() == 0 and info.st_uid != 0)):
            raise RuntimeError('unsafe lifecycle lock; expected a root-owned regular file')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not allow_migration and (MIGRATION_JOURNAL.exists() or MIGRATION_JOURNAL.is_symlink()):
            raise RuntimeError('unfinished migration journal; preserve files and inspect recovery instructions')
    except BaseException:
        os.close(fd)
        raise
    return fd


def legacy_publish_lock():
    fd = os.open(ETC/'.publish.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or
                (os.geteuid() == 0 and info.st_uid != 0)):
            raise RuntimeError('unsafe legacy publish lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def verify_running_dns(state):
    """Check the active listener's positive A record; a state hash alone is not liveness."""
    cfg = state.get('config')
    if not isinstance(cfg, str):
        raise RuntimeError('running configuration absent')
    props = {}
    for line in cfg.splitlines():
        if line.startswith(('port=', 'listen-address=', 'host-record=')):
            k, v = line.split('=', 1)
            if k in props:
                raise RuntimeError('ambiguous running configuration')
            props[k] = v
    try:
        port = int(props['port'])
        listen = str(ipaddress.IPv4Address(props['listen-address']))
        host, address, _ = props['host-record'].split(',')
        if not host.startswith('health-') or not host.endswith('.capstone.test'):
            raise RuntimeError('missing local health marker')
        if address != '192.0.2.1':
            raise RuntimeError('unexpected health address')
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError('invalid running DNS configuration') from exc
    sys.path.insert(0, str(ROOT/'apps'/'dns-agent'/'src'))
    from dns_agent.runtime import dns_rcode
    if dns_rcode(host, 1, port, server_ip=listen, require_answer=True,
                 expected_rdata=socket.inet_pton(socket.AF_INET, address)) != 0:
        raise RuntimeError('running DNS health probe returned an invalid answer')


def await_published_policy(digest: str, *, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not service_active():
            raise RuntimeError('DNS service became inactive after publishing')
        try:
            from dns_agent.transaction import read_regular
            state = json.loads(read_regular(STATE_DIR/'state.json', 4*1024*1024))
            if state.get('policy_sha256') == digest:
                verify_running_dns(state)
                return
        except (FileNotFoundError, ValueError, RuntimeError, OSError):
            pass
        time.sleep(.25)
    raise RuntimeError('policy saved but live DNS did not confirm; inspect journalctl/state; no automatic downgrade')

def attest(args):
    """Read-only signed-policy reconciliation for repeat apply ticks.

    The policy on disk, daemon-acknowledged SHA, local health answer, and
    dedicated nftables firewall must all agree. Never installs or mutates DNS.
    """
    need_root()
    expected = args.policy_sha256
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("attest requires a lowercase SHA-256 policy digest")
    lock = publish_lock()
    try:
        read_options()
        verify_installed_code()
        if not service_active():
            raise RuntimeError("DNS service inactive; cannot attest policy")
        current = validate_policy(ETC/'policy.json', installed=True)
        if current.digest != expected:
            raise RuntimeError("published DNS policy differs from signed snapshot")
        await_published_policy(expected)
        firewall_guard('verify')
        print("DNS_ATTESTED:", expected)
    finally:
        os.close(lock)


def install(args):
    # Detecting a subnet cannot itself grant access to clients.
    # Fail before any root check, lock, or network lookup if scope is not approved.
    if args.apply and args.client_cidr is None:
        raise ValueError('--apply requires an explicit --client-cidr; inspect the preview first')
    automatic_listener = args.listen_ip is None
    automatic_interface = args.interface is None
    suggested_scope = None
    if automatic_listener:
        listen_ip, interface, suggested_scope = discover_listener_interface(None, args.interface)
    else:
        listen_ip = args.listen_ip
        if automatic_interface or args.client_cidr is None:
            interface, suggested_scope = discover_listener_interface(listen_ip, args.interface)
        else:
            interface = args.interface
    scope = args.client_cidr if args.client_cidr is not None else suggested_scope
    listen, interface, subnet, upstream, upstream_port = parse_options(
        listen_ip, interface, scope, args.upstream, args.upstream_port)
    policy = validate_policy(args.policy)
    dns, guard = unit_files(listen, upstream, upstream_port, subnet)
    token = secrets.token_hex(16)
    firewall = firewall_rules(listen, interface, subnet, token)
    print('Listener:', f'{listen}:53 UDP/TCP', 'interface:', interface)
    if automatic_listener:
        print('Auto-detected listen IP / interface:', listen, '/', interface)
    elif automatic_interface:
        print('Auto-detected interface owning listener IP:', interface)
    if args.client_cidr is None:
        print('SUGGESTED client CIDR (preview only, NOT approved):', subnet)
        print('Review permitted client addresses, then provide --client-cidr', subnet, '--apply')
    else:
        print('Explicitly approved client scope:', subnet,
              '(only this interface; host loopback for checks)')
    print('Upstream:', f'{upstream}:{upstream_port}', 'policy SHA-256:', policy.digest)
    print('Mutates /opt/aleph-dns, /etc/aleph-dns, two systemd units, nft inet aleph_dns and /run lock')
    print('Does not change /etc/resolv.conf, other DNS services or router/DHCP settings')
    if not args.apply:
        print('PREVIEW ONLY: --apply performs environment checks and changes system services')
        return
    need_root()
    fd = publish_lock()
    try:
        _install_locked(args, listen, interface, subnet, upstream, upstream_port,
                        policy, dns, guard, firewall, token)
    finally:
        os.close(fd)


def _install_locked(args, listen, interface, subnet, upstream, upstream_port,
                    policy, dns, guard, firewall, token):
    if any(p.exists() or p.is_symlink() for p in (
            ETC, CODE.parent, STATE_DIR, UNIT_DIR/'aleph-dns.service',
            UNIT_DIR/'aleph-dns-firewall.service')):
        raise RuntimeError('existing or partial ALEPH installation: refuse overwrite; inspect and recover')
    for path in ('/usr/bin/python3', '/usr/sbin/nft'):
        if not Path(path).is_file():
            raise RuntimeError(f'missing required executable: {path}')
    if not shutil.which('dnsmasq') or not shutil.which('ip'):
        raise RuntimeError('install dnsmasq-base, iproute2 and nftables first')
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer required')
    check_service_python()
    check_parent_ip_allows(listen, subnet, upstream)
    inspect_interface(listen, interface)
    check_free_port(listen)
    if table_exists():
        raise RuntimeError('reserved nft inet aleph_dns table already exists; will not flush another owner')
    subprocess.run(['/usr/sbin/nft', '-c', '-f', '/dev/stdin'],
                   input=firewall, text=True, timeout=8, check=True)
    source = ROOT/'apps'/'dns-agent'/'src'
    if any(path.is_symlink() for path in (CODE.parent, *CODE.parents)):
        raise RuntimeError('unsafe symlink in /opt/aleph-dns installation path')
    if any(path.is_symlink() for path in source.rglob('*')):
        raise RuntimeError('refusing to install source containing symlinks')
    created_account = False
    owned = {}
    try:
        try:
            account = pwd.getpwnam(USER)
        except KeyError:
            subprocess.run(['useradd', '--system', '--user-group', '--no-create-home',
                            '--home-dir', str(STATE_DIR),
                            '--shell', '/usr/sbin/nologin', USER], check=True)
            created_account = True
            account = pwd.getpwnam(USER)
        if (account.pw_uid == 0 or grp.getgrnam(USER).gr_gid != account.pw_gid
                or account.pw_dir != str(STATE_DIR)
                or not account.pw_shell.endswith('/nologin')):
            raise RuntimeError('unsafe or inconsistent service account')
        ETC.mkdir(mode=0o750, exist_ok=False)
        record_directory(ETC, owned)
        os.chown(ETC, 0, account.pw_gid)
        CODE.parent.mkdir(mode=0o755, parents=True, exist_ok=False)
        record_directory(CODE.parent, owned)
        STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=False)
        record_directory(STATE_DIR, owned)
        os.chown(STATE_DIR, account.pw_uid, account.pw_gid)
        shutil.copytree(source, CODE, symlinks=False,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        normalize_installed_code(CODE)
        record_directory(CODE, owned)
        remember_static(CODE.parent, owned)
        write_owned_atomic(ETC/'policy.json', policy.raw + b'\n', 0o640, 0, account.pw_gid, owned)
        write_owned_atomic(CODE.parent/'firewall_guard.py',
                           Path(__file__).with_name('firewall_guard.py').read_bytes(), 0o644, 0, 0, owned)
        write_owned_atomic(ETC/'firewall.json', json.dumps({'listen': listen, 'interface': interface,
                           'subnet': subnet, 'token': token}).encode()+b'\n', 0o600, 0, 0, owned)
        write_owned_atomic(ETC/'options.json',
                           json.dumps({'managed_by': OWNERSHIP_MARKER}).encode()+b'\n',
                           0o600, 0, 0, owned)
        write_owned_atomic(ETC/'installed-code.json',
                           json.dumps({'managed_by': OWNERSHIP_MARKER,
                                       'contents': installed_code_inventory()}, sort_keys=True).encode()+b'\n',
                           0o600, 0, 0, owned)
        remember_static(ETC, owned)
        remember_static(CODE.parent, owned)
        write_new(UNIT_DIR/'aleph-dns-firewall.service', guard.encode(), 0o644, 0, 0, owned)
        write_new(UNIT_DIR/'aleph-dns.service', dns.encode(), 0o644, 0, 0, owned)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'aleph-dns-firewall.service'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'aleph-dns.service'], check=True)
        await_installed_dns(policy, listen=listen, upstream=upstream,
                            upstream_port=upstream_port)
    except Exception as original:
        try:
            cleanup_failed_install(owned=owned, remove_service_account=created_account, remove_state=True)
        except Exception as rollback:
            raise RuntimeError(f'install failed: {original}; rollback incomplete: {rollback}') from original
        raise RuntimeError(f'install failed and was rolled back: {original}') from original
    print('VERIFIED: DNS responded on', f'{listen}:53', 'with policy', policy.digest)
    print('Before updating DHCP option 6, query UDP/TCP from a permitted LAN client')


def publish(args):
    need_root()
    fd = publish_lock()
    try:
        read_options()  # Reject old installations until a verified upgrade.
        verify_installed_code()
        if not service_active():
            raise RuntimeError('DNS service inactive; do not publish to a stopped resolver')
        policy = validate_policy(args.policy, installed=True)
        from dns_agent.policy import parse_policy
        from dns_agent.transaction import read_regular
        current_path = ETC/'policy.json'
        # An expired previously published file must not prevent recovery.
        current = parse_policy(read_regular(current_path))
        # Reject publishing while a transaction is recovering or the runtime state is absent.
        if (STATE_DIR/'pending.json').exists():
            raise RuntimeError('pending DNS recovery; inspect state before publishing')
        try:
            state = json.loads(read_regular(STATE_DIR/'state.json', 4*1024*1024))
            acknowledged = parse_policy(state['policy'].encode())
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            raise RuntimeError('cannot verify currently running policy; refuse publish') from exc
        for previous in (current, acknowledged):
            if (policy.issued_at < previous.issued_at or
                    (policy.issued_at == previous.issued_at and policy.digest != previous.digest)):
                raise RuntimeError('stale or conflicting issuance; keep current policy')
        if policy.digest == current.digest:
            await_published_policy(policy.digest)
            print('UNCHANGED and ACKNOWLEDGED:', policy.digest)
            return
        account = pwd.getpwnam(USER)
        write_atomic(current_path, policy.raw+b'\n', 0o640, 0, account.pw_gid)
        await_published_policy(policy.digest)
        print('APPLIED:', policy.digest, '— DNS agent acknowledged the policy')
    finally:
        os.close(fd)


def upgrade(args):
    if not args.apply:
        print('PREVIEW: migrate an existing ALEPH installation; preserves policy and state in a private backup.')
        print('Legacy unmarked tables require --adopt-legacy-table after operator verification.')
        return
    need_root()
    fd = publish_lock(allow_migration=True)
    try:
        if MIGRATION_JOURNAL.exists() or MIGRATION_JOURNAL.is_symlink():
            raise RuntimeError('unfinished migration journal; preserve files and inspect recovery instructions')
        legacy_fd = legacy_publish_lock()
        try:
            existing = inspect_existing()
            if existing['legacy'] and not args.adopt_legacy_table:
                raise RuntimeError('legacy table has no owner marker; --adopt-legacy-table requires operator verification')
            # Check before stopping either unit or creating a migration archive.
            check_service_python()
            listen, _, subnet, upstream, _ = existing['options']
            check_parent_ip_allows(listen, subnet, upstream)
            if getattr(args, 'preserve_expired_policy', False):
                migrate_existing(existing, 'upgrade', preserve_expired=True)
            else:
                migrate_existing(existing, 'upgrade')
        finally:
            os.close(legacy_fd)
    finally:
        os.close(fd)


def migration_snapshot(config, legacy):
    gen, entries = _guard.snapshot()
    if entries:
        handle = (_guard.checked_legacy_handle(config, entries) if legacy
                  else _guard.checked_handle(config, entries))
    else:
        handle = None
    _guard.require_generation_guard(gen)
    return gen, handle


@contextmanager
def migration_firewall_lock():
    fd = os.open(_guard.LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022):
            raise RuntimeError('unsafe firewall lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_private_tree(source, destination):
    """Copy regular files only, verify bytes, and sync the private archive."""
    for path in (source, *source.rglob('*')):
        info = path.lstat()
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise RuntimeError(f'unsupported backup entry: {path}')
    shutil.copytree(source, destination, symlinks=False)
    for path in (source, *source.rglob('*')):
        copy = destination if path == source else destination/path.relative_to(source)
        info = path.lstat()
        os.chown(copy, info.st_uid, info.st_gid, follow_symlinks=False)
        copy.chmod(stat.S_IMODE(info.st_mode))
        saved = copy.lstat()
        if (saved.st_uid, saved.st_gid, stat.S_IMODE(saved.st_mode)) != (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)):
            raise RuntimeError(f'backup ownership verification failed: {path}')
        if path.is_file():
            if path.read_bytes() != copy.read_bytes():
                raise RuntimeError(f'backup verification failed: {path}')
            with copy.open('rb') as inp:
                os.fsync(inp.fileno())
    for directory in sorted((p for p in destination.rglob('*') if p.is_dir()), reverse=True):
        sync_directory(directory)
    sync_directory(destination)
    sync_directory(destination.parent)


def migration_record(archive, action, phase):
    manifest = archive/'backup-manifest.json'
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None
    write_atomic(MIGRATION_JOURNAL, json.dumps({'archive': str(archive), 'action': action,
                 'phase': phase, 'backup_sha256': digest}).encode()+b'\n', 0o600, 0, 0)


def backup_inventory(archive):
    records = {}
    for path in sorted(archive.rglob('*')):
        if path == archive/'backup-manifest.json':
            continue
        info = path.lstat()
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise RuntimeError(f'unsafe backup entry: {path}')
        record = {'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}
        if stat.S_ISDIR(info.st_mode):
            record['kind'] = 'directory'
        else:
            record['kind'] = 'file'
            with path.open('rb') as stream:
                record['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        records[path.relative_to(archive).as_posix()] = record
    return records


def migration_status():
    """Read-only diagnosis; never restore old state over a possibly newer policy."""
    need_root()
    journal = json.loads(protected_text(MIGRATION_JOURNAL, forbidden=0o077))
    if not isinstance(journal, dict) or set(journal) != {'archive', 'action', 'phase', 'backup_sha256'}:
        raise RuntimeError('invalid migration journal; preserve for inspection')
    archive = Path(journal['archive'])
    if archive.parent != BACKUP_DIR or not archive.name.startswith('aleph-dns-migration-'):
        raise RuntimeError('invalid migration archive path')
    info = archive.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise RuntimeError('unsafe migration archive')
    digest = journal['backup_sha256']
    if digest is None:
        backup_status = 'incomplete; original installation may still be needed'
    else:
        manifest_text = protected_text(archive/'backup-manifest.json', forbidden=0o077)
        if hashlib.sha256(manifest_text.encode()).hexdigest() != digest:
            raise RuntimeError('backup manifest digest mismatch')
        if json.loads(manifest_text) != backup_inventory(archive):
            raise RuntimeError('backup content or metadata mismatch')
        backup_status = 'verified'
    print('Migration:', journal['action'], 'phase:', journal['phase'], 'backup:', archive, backup_status)
    try:
        uid = pwd.getpwnam(USER).pw_uid
        current = json.loads(protected_text(STATE_DIR/'state.json', forbidden=0o077, owner=uid))
        prior = json.loads(protected_text(archive/'state'/'state.json', forbidden=0o077, owner=uid))
        before, now = prior['policy_sha256'], current['policy_sha256']
        if not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                   for value in (before, now)):
            raise ValueError('invalid digest')
        print('Saved policy digest:', before, 'current state digest:', now,
              '(equal)' if before == now else '(different; do not restore older state)')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        print('Current or backed-up policy state cannot be compared; preserve both for inspection.')
    print('A newer policy may have been accepted after restart. Do not overwrite current policy or state from this backup.')
    print('Keep the journal, current files and backup; inspect service status and reconcile manually.')


def migration_state():
    """Validate saved state without importing any old installed source."""
    sys.path.insert(0, str(ROOT/'apps'/'dns-agent'/'src'))
    from dns_agent.policy import parse_policy
    from dns_agent.transaction import Store, read_regular
    if (STATE_DIR/'pending.json').exists() or (STATE_DIR/'pending.json').is_symlink():
        raise RuntimeError('pending DNS transaction; preserve state for recovery')
    protected_text(ETC/'policy.json')
    uid = pwd.getpwnam(USER).pw_uid
    for path in STATE_DIR.iterdir():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077):
            raise RuntimeError(f'unsafe DNS state file: {path}')
    policy = parse_policy(read_regular(ETC/'policy.json'))
    state = Store(STATE_DIR).read_state()
    if state is None:
        raise RuntimeError('saved DNS state missing; preserve files for manual recovery')
    previous = parse_policy(state['policy'].encode())
    if (policy.issued_at < previous.issued_at or
            (policy.issued_at == previous.issued_at and policy.digest != previous.digest)):
        raise RuntimeError('published policy is older than or conflicts with saved state')
    return policy, state


def migrate_existing(existing, action, *, preserve_expired=False):
    """A stopped service and a durable backup precede every destructive step.

    Interrupted operations retain their journal; they are not automatically
    rolled back over state that a newer resolver may already have accepted.
    """
    # The running agent owns the state lock until stopped.  Check only the
    # protected published policy while both lifecycle locks are held; its
    # state and freshness are checked again after the agent releases its lock.
    # An already expired policy must not take an otherwise working DNS down.
    def check_upgrade_policy():
        if action == 'upgrade':
            protected_text(ETC/'policy.json')
            if preserve_expired:
                validate_policy(ETC/'policy.json', allow_expired=True)
            else:
                validate_policy(ETC/'policy.json')

    check_upgrade_policy()
    listen, interface, subnet, upstream, port = existing['options']
    config = existing.get('config') or {'listen': listen, 'interface': interface,
                                        'subnet': subnet, 'token': secrets.token_hex(16)}
    migration_snapshot(config, existing['legacy'])
    if BACKUP_DIR.is_symlink():
        raise RuntimeError('unsafe backup directory symlink')
    BACKUP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup_info = BACKUP_DIR.lstat()
    if (not stat.S_ISDIR(backup_info.st_mode) or backup_info.st_mode & 0o022 or
            (os.geteuid() == 0 and backup_info.st_uid != 0)):
        raise RuntimeError('unsafe backup directory ownership or mode')
    archive = Path(tempfile.mkdtemp(prefix='aleph-dns-migration-', dir=BACKUP_DIR))
    archive.chmod(0o700)
    previous_inventory = existing.get('inventory')
    if previous_inventory is not None and installed_code_inventory(allow_historical_src=existing['historical']) != previous_inventory:
        raise RuntimeError('installed code changed since inspection')
    copy_private_tree(CODE.parent, archive/'code')
    if previous_inventory is not None and (
            installed_code_inventory(base=archive/'code', allow_historical_src=existing['historical']) != previous_inventory or
            installed_code_inventory(allow_historical_src=existing['historical']) != previous_inventory):
        raise RuntimeError('installed code changed during backup')
    units = archive/'units'
    units.mkdir(mode=0o700)
    for name in ('aleph-dns.service', 'aleph-dns-firewall.service'):
        info = (UNIT_DIR/name).stat()
        write_new(units/name, protected_text(UNIT_DIR/name).encode(), stat.S_IMODE(info.st_mode),
                  info.st_uid, info.st_gid, {})
    sync_directory(units)
    sync_directory(archive)
    sync_directory(BACKUP_DIR)
    # Copying a large installation can take time: recheck before writing a
    # recovery journal or stopping a service.  Keep the post-stop check too,
    # because expiration and unsynchronized external edits can race this check.
    check_upgrade_policy()
    migration_record(archive, action, 'prepared')
    for name in ('aleph-dns.service', 'aleph-dns-firewall.service'):
        subprocess.run(['systemctl', 'disable', '--now', name], timeout=20, check=True)
        enabled = subprocess.run(['systemctl', 'is-enabled', name], capture_output=True, text=True, timeout=10)
        active = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True, timeout=10)
        if enabled.stdout.strip() != 'disabled' or active.stdout.strip() not in ('inactive', 'failed'):
            raise RuntimeError(f'cannot confirm disabled and stopped unit: {name}')
    migration_record(archive, action, 'stopped')
    lockfd = os.open(STATE_DIR/'lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(lockfd).st_mode):
            raise RuntimeError('unsafe DNS state lock')
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        copy_private_tree(ETC, archive/'config')
        copy_private_tree(STATE_DIR, archive/'state')
        sync_directory(archive)
        policy, state = migration_state()
        if previous_inventory is not None and installed_code_inventory(allow_historical_src=existing['historical']) != previous_inventory:
            raise RuntimeError('installed code changed after backup; preserve for inspection')
        write_atomic(archive/'backup-manifest.json', json.dumps(backup_inventory(archive), sort_keys=True).encode()+b'\n', 0o600, 0, 0)
        sync_directory(archive)
        if action == 'upgrade' and not preserve_expired and policy.expires_at <= datetime.now(timezone.utc):
            raise RuntimeError('expired policy preserved in backup; publish a valid policy after recovery')
        migration_record(archive, action, 'state-backed-up')
        with migration_firewall_lock():
            gen, handle = migration_snapshot(config, existing['legacy'])
            if handle is not None and (existing['legacy'] or action == 'uninstall'):
                _guard.delete_with_generation(gen, handle)
        migration_record(archive, action, 'firewall-checked')
        if action == 'uninstall':
            for name in ('aleph-dns.service', 'aleph-dns-firewall.service'):
                (UNIT_DIR/name).unlink()
            sync_directory(UNIT_DIR)
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            for directory in (ETC, STATE_DIR, CODE.parent):
                shutil.rmtree(directory)
                sync_directory(directory.parent)
            migration_record(archive, action, 'complete')
        else:
            source = ROOT/'apps'/'dns-agent'/'src'
            if any(p.is_symlink() for p in (source, *source.rglob('*'))):
                raise RuntimeError('refusing to copy source containing symlinks')
            stage = CODE.parent/'src.migration-new'
            old = CODE.parent/'src.migration-old'
            if stage.exists() or old.exists() or stage.is_symlink() or old.is_symlink():
                raise RuntimeError('migration staging paths already exist')
            shutil.copytree(source, stage, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
            normalize_installed_code(stage)
            for path in stage.rglob('*'):
                if path.is_file():
                    with path.open('rb') as stream:
                        os.fsync(stream.fileno())
            for path in sorted((p for p in stage.rglob('*') if p.is_dir()), reverse=True):
                sync_directory(path)
            sync_directory(stage)
            sync_directory(CODE.parent)
            os.rename(CODE, old)
            os.rename(stage, CODE)
            sync_directory(CODE.parent)
            shutil.rmtree(old)
            sync_directory(CODE.parent)
            write_atomic(CODE.parent/'firewall_guard.py', Path(__file__).with_name('firewall_guard.py').read_bytes(), 0o644, 0, 0)
            write_atomic(ETC/'firewall.json', json.dumps(config).encode()+b'\n', 0o600, 0, 0)
            write_atomic(ETC/'installed-code.json', json.dumps({'managed_by': OWNERSHIP_MARKER,
                         'contents': installed_code_inventory()}, sort_keys=True).encode()+b'\n', 0o600, 0, 0)
            # Upgrade removes the retired flag from the on-disk installation.
            # The original options and units are retained in the verified archive.
            write_atomic(ETC/'options.json',
                         json.dumps({'managed_by': OWNERSHIP_MARKER}).encode()+b'\n',
                         0o600, 0, 0)
            dns, fw = unit_files(listen, upstream, port, subnet)
            write_atomic(UNIT_DIR/'aleph-dns.service', dns.encode(), 0o644, 0, 0)
            write_atomic(UNIT_DIR/'aleph-dns-firewall.service', fw.encode(), 0o644, 0, 0)
            migration_record(archive, action, 'new-files')
            with migration_firewall_lock():
                _guard.apply(config)
            migration_record(archive, action, 'new-firewall')
    finally:
        os.close(lockfd)
    if action == 'upgrade':
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'aleph-dns-firewall.service'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'aleph-dns.service'], check=True)
        await_installed_dns(policy, listen=listen, upstream=upstream, upstream_port=port)
        migration_record(archive, action, 'complete')
    MIGRATION_JOURNAL.unlink()
    descriptor = os.open(MIGRATION_JOURNAL.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(action.upper(), 'VERIFIED; original configuration and state retained at', archive)


def uninstall(args):
    if not args.apply:
        print('PREVIEW: stops two ALEPH services and its nft table; preserves policy/state in a root-only archive.')
        print('Change client DHCP/manual DNS to a working resolver before using uninstall --apply.')
        return
    need_root()
    fd = publish_lock(allow_migration=True)
    try:
        if MIGRATION_JOURNAL.exists() or MIGRATION_JOURNAL.is_symlink():
            raise RuntimeError('unfinished migration journal; preserve files and inspect recovery instructions')
        legacy_fd = legacy_publish_lock()
        try:
            existing = inspect_existing()
            if existing['legacy'] and not getattr(args, 'adopt_legacy_table', False):
                raise RuntimeError('legacy table has no owner marker; --adopt-legacy-table requires operator verification')
            migrate_existing(existing, 'uninstall')
        finally:
            os.close(legacy_fd)
    finally:
        os.close(fd)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cmds = cli.add_subparsers(dest='command', required=True)
    setup = cmds.add_parser('install', help='preview by default; --apply modifies system')
    setup.add_argument('--listen-ip',
                       help='optional; auto-detect unique active private IPv4 if omitted')
    setup.add_argument('--interface',
                       help='optional; select NIC when auto-detection is ambiguous')
    setup.add_argument('--client-cidr',
                       help='required explicitly for --apply; preview suggests /24 or narrower')
    setup.add_argument('--upstream', required=True, help='trusted upstream IPv4 DNS server')
    setup.add_argument('--policy', type=Path, required=True)
    setup.add_argument('--upstream-port', type=int, default=53)
    setup.add_argument('--apply', action='store_true')
    update = cmds.add_parser('publish', help='publish an approved policy; requires sudo')
    update.add_argument('--policy', type=Path, required=True)
    reconcile = cmds.add_parser('attest', help='read-only check of signed policy actually active in DNS')
    reconcile.add_argument('--policy-sha256', required=True)
    migration = cmds.add_parser('upgrade', help='migrate existing installation; preview by default')
    migration.add_argument('--apply', action='store_true')
    migration.add_argument('--adopt-legacy-table', action='store_true')
    migration.add_argument('--preserve-expired-policy', action='store_true',
                           help='explicitly retain an expired policy during upgrade; expired blocks remain inactive')
    cmds.add_parser('migration-status', help='diagnose an interrupted migration without restoring state')
    remove = cmds.add_parser('uninstall', help='preview by default; stop service and archive data')
    remove.add_argument('--apply', action='store_true')
    remove.add_argument('--adopt-legacy-table', action='store_true')
    args = cli.parse_args(argv)
    try:
        if args.command == 'install':
            install(args)
        elif args.command == 'publish':
            publish(args)
        elif args.command == 'attest':
            attest(args)
        elif args.command == 'upgrade':
            upgrade(args)
        elif args.command == 'migration-status':
            migration_status()
        else:
            uninstall(args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            PermissionError, KeyError) as exc:
        cli.exit(2, f'ERROR: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
