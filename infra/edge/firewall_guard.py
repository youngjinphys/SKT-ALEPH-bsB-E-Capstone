#!/usr/bin/env python3
"""Manage only a completely verified ALEPH nft table.

A kernel ruleset generation ID makes the validated snapshot and deletion one
optimistic transaction, including against writers that do not use our lock.
"""
import argparse
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import subprocess

NFT = '/usr/sbin/nft'
LOCK = '/run/aleph-dns-firewall.lock'
TABLE = 'aleph_dns'
PREFIX = 'skt-aleph-dns-v1:'


def validate_config(config):
    if not isinstance(config, dict) or set(config) != {'token', 'listen', 'interface', 'subnet'}:
        raise RuntimeError('invalid firewall configuration')
    try:
        ip = ipaddress.IPv4Address(config['listen'])
        net = ipaddress.IPv4Network(config['subnet'], strict=True)
        if (not isinstance(config['token'], str) or not re.fullmatch('[0-9a-f]{32}', config['token'])
                or not isinstance(config['interface'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', config['interface'])
                or str(ip) != config['listen'] or str(net) != config['subnet']):
            raise ValueError('invalid value')
    except (ValueError, TypeError) as exc:
        raise RuntimeError('invalid firewall configuration') from exc


def render(config):
    validate_config(config)
    listen, interface, subnet = (config[x] for x in ('listen', 'interface', 'subnet'))
    rules = [f'create table inet {TABLE}',
             f'add chain inet {TABLE} input {{ type filter hook input priority -100; policy accept; }}']
    for proto in ('udp', 'tcp'):
        target = f'ip daddr {listen} {proto} dport 53'
        rules.append(f'add rule inet {TABLE} input {target} iifname != "lo" iifname != "{interface}" drop comment "{PREFIX}{config["token"]}"')
        rules.append(f'add rule inet {TABLE} input {target} iifname "{interface}" ip saddr != {subnet} drop comment "{PREFIX}{config["token"]}"')
    return '\n'.join(rules) + '\n'


def expected(config):
    validate_config(config)
    def match(left, op, right):
        return {'match': {'op': op, 'left': left, 'right': right}}
    def payload(proto, field): return {'payload': {'protocol': proto, 'field': field}}
    def meta(): return {'meta': {'key': 'iifname'}}
    network = ipaddress.IPv4Network(config['subnet'])
    prefix = {'prefix': {'addr': str(network.network_address), 'len': network.prefixlen}}
    # nft prints /32 as a plain address instead of a prefix object.
    if network.prefixlen == 32:
        prefix = str(network.network_address)
    records = [{'table': {'family': 'inet', 'name': TABLE}},
               {'chain': {'family': 'inet', 'table': TABLE, 'name': 'input',
                          'type': 'filter', 'hook': 'input', 'prio': -100, 'policy': 'accept'}}]
    for proto in ('udp', 'tcp'):
        common = [match(payload('ip', 'daddr'), '==', config['listen']),
                  match(payload(proto, 'dport'), '==', 53)]
        for suffix in ([match(meta(), '!=', 'lo'), match(meta(), '!=', config['interface'])],
                       [match(meta(), '==', config['interface']), match(payload('ip', 'saddr'), '!=', prefix)]):
            records.append({'rule': {'family': 'inet', 'table': TABLE, 'chain': 'input',
                                     'expr': common + suffix + [{'drop': None}],
                                     'comment': PREFIX + config['token']}})
    return records


def checked_handle(config, entries, *, legacy=False):
    cleaned = []
    handle = None
    for entry in entries:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise RuntimeError('firewall ownership or contents do not match')
        kind, value = next(iter(entry.items()))
        if kind == 'metainfo':
            continue
        if not isinstance(value, dict):
            raise RuntimeError('firewall ownership or contents do not match')
        value = value.copy()
        obj_handle = value.pop('handle', None)
        if kind == 'table':
            handle = obj_handle
        cleaned.append({kind: value})
    wanted = expected(config)
    if legacy:
        for entry in wanted:
            if 'rule' in entry:
                del entry['rule']['comment']
    if cleaned != wanted or type(handle) is not int or handle <= 0:
        raise RuntimeError('firewall ownership or contents do not match; manual inspection required')
    return handle


def checked_legacy_handle(config, entries):
    """Compare the complete unmarked legacy table; this does not prove ownership."""
    return checked_handle(config, entries, legacy=True)


def message(kind, flags, seq, payload):
    return struct.pack('IHHII', 16 + len(payload), kind, flags, seq, 0) + payload


def attribute(kind, value):
    length = 4 + len(value)
    return struct.pack('HH', length, kind) + value + b'\0' * (-length % 4)


def nfgen(family=0, resource=0):
    return struct.pack('!BBH', family, 0, resource)


def netlink_socket():
    sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 12)  # NETLINK_NETFILTER
    sock.settimeout(5)
    sock.bind((0, 0))
    return sock


def generation():
    with netlink_socket() as sock:
        sock.send(message(0xA10, 1, 1, nfgen()))  # NFT_MSG_GETGEN
        data = sock.recv(65536)
    if len(data) < 28:
        raise RuntimeError('cannot read nftables generation')
    length, kind, _, seq, _ = struct.unpack_from('IHHII', data)
    if kind != 0xA0F or seq != 1 or length > len(data):
        raise RuntimeError('cannot read nftables generation')
    offset = 20
    while offset + 4 <= length:
        size, tag = struct.unpack_from('HH', data, offset)
        if size < 4 or offset + size > length:
            break
        if tag == 1 and size == 8:
            return struct.unpack_from('!I', data, offset + 4)[0]
        offset += (size + 3) & ~3
    raise RuntimeError('cannot read nftables generation')


def run_nft(args, **kwargs):
    return subprocess.run([NFT, *args], text=True, timeout=10, check=True, **kwargs)


def snapshot():
    before = generation()
    # Listing tables avoids interpreting an arbitrary list-table error as absence.
    listing = run_nft(['-j', 'list', 'tables'], capture_output=True)
    try:
        tables = json.loads(listing.stdout)['nftables']
        found = any(isinstance(e, dict) and e.get('table', {}).get('family') == 'inet'
                    and e['table'].get('name') == TABLE for e in tables)
        entries = json.loads(run_nft(['-j', '-a', '-n', 'list', 'table', 'inet', TABLE],
                                     capture_output=True).stdout)['nftables'] if found else []
        # nft 1.0.x omits table/chain comments from JSON; text retains them.
        if found:
            rendered = run_nft(['-a', 'list', 'table', 'inet', TABLE], capture_output=True).stdout
            if re.search(r'^\s*comment\s', rendered, re.MULTILINE):
                raise RuntimeError('firewall ownership or contents do not match; unexpected object comment')
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RuntimeError('cannot inspect nftables ownership') from exc
    if generation() != before:
        raise RuntimeError('nftables changed during inspection; retry')
    return before, entries


def require_generation_guard(gen):
    """Confirm the kernel rejects a stale batch before allowing deletion.

    The probe creates and deletes a unique inert table in the same atomic
    batch. If an old kernel ignores the generation attribute, the batch leaves
    no table behind and its successful acknowledgement is treated as failure.
    """
    if gen == 0:
        raise RuntimeError('zero nftables generation cannot guard deletion')
    mismatch = (gen + 1) & 0xffffffff or 1
    name = ('aleph_probe_' + secrets.token_hex(16)).encode() + b'\0'
    request = (message(16, 1, 2, nfgen(0, 10) + attribute(1, struct.pack('!I', mismatch)))
               + message(0xA00, 0x605, 3, nfgen(1) + attribute(1, name))
               + message(0xA02, 5, 4, nfgen(1) + attribute(1, name))
               + message(17, 1, 5, nfgen(0, 10)))
    with netlink_socket() as sock:
        sock.send(request)
        data = sock.recv(65536)
    if len(data) < 20:
        raise RuntimeError('kernel generation guard probe failed')
    length, kind, _, seq, _ = struct.unpack_from('IHHII', data)
    error = struct.unpack_from('i', data, 16)[0]
    if length > len(data) or kind != 2 or seq != 2 or error != -85:  # ERESTART
        raise RuntimeError('kernel did not reject stale nftables generation; refusing deletion')


def delete_with_generation(gen, handle):
    # NFNL_BATCH_GENID rejects the whole transaction if ANY ruleset writer
    # changed anything after the snapshot. The table handle prevents deleting a
    # same-name replacement even if a generation ID eventually wraps.
    request = (message(16, 1, 2, nfgen(0, 10) + attribute(1, struct.pack('!I', gen)))
               + message(0xA02, 5, 3, nfgen(1) + attribute(4, struct.pack('!Q', handle)))
               + message(17, 1, 4, nfgen(0, 10)))
    with netlink_socket() as sock:
        sock.send(request)
        data = sock.recv(65536)
    if len(data) < 20:
        raise RuntimeError('nftables delete acknowledgement missing')
    length, kind, _, seq, _ = struct.unpack_from('IHHII', data)
    if length > len(data) or kind != 2 or seq != 3:
        raise RuntimeError('nftables delete rejected or unacknowledged')
    error = struct.unpack_from('i', data, 16)[0]
    if error:
        raise OSError(-error, 'nftables changed or delete was rejected')


def apply(config):
    gen, entries = snapshot()
    if entries:
        checked_handle(config, entries)
    require_generation_guard(gen)
    if entries:
        return
    # create, never add: a concurrent creator makes the whole transaction fail.
    run_nft(['-f', '/dev/stdin'], input=render(config), capture_output=True)
    _, entries = snapshot()
    checked_handle(config, entries)


def remove(config):
    gen, entries = snapshot()
    if entries:
        handle = checked_handle(config, entries)
        require_generation_guard(gen)
        delete_with_generation(gen, handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['apply', 'remove', 'verify', 'check'])
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    fd = os.open(args.config, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise RuntimeError('unsafe firewall configuration ownership or mode')
        with os.fdopen(fd, 'r') as stream:
            fd = -1
            config = json.load(stream)
    finally:
        if fd != -1:
            os.close(fd)
    validate_config(config)
    lock = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('unsafe firewall lock')
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'apply': apply(config)
        elif args.action == 'remove': remove(config)
        else:
            _, entries = snapshot()
            if not entries:
                if args.action == 'verify': raise RuntimeError('firewall table missing')
            else:
                checked_handle(config, entries)
    finally:
        os.close(lock)


if __name__ == '__main__':
    main()
