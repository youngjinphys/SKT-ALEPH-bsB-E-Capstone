"""Bounded aggregate-only DNS diagnostics. No packet capture or query logging.

CHAOS TXT counters are opt-in and describe dnsmasq's cache, not user browsing
or blocked-request totals. Probe durations describe synthetic canaries only.
"""
from __future__ import annotations
import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import socket
import struct
from dns_agent.runtime import _dns_name
from .snapshot import timestamp

COUNTERS = ('hits', 'misses', 'evictions', 'insertions', 'size')
HOST_FIELDS = ('uptime_s', 'boot_id', 'load_1m', 'memory_used_pct', 'disk_used_pct')
MAX_COUNTER = 2**53 - 1

def blank_metrics(*, extended=False):
    result = {'host': dict.fromkeys(HOST_FIELDS), 'cache': None, 'checks': [],
              'policy': {'valid_until': None, 'active_blocks': None}}
    if extended:
        from .system_metrics import blank_system
        result['system'] = blank_system()
    return result

def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Unexpected aggregate metric fields')

def _number(value, maximum, *, integer=False):
    if value is None:
        return
    if (type(value) not in ((int,) if integer else (int, float))
            or not 0 <= value <= maximum or not math.isfinite(value)):
        raise ValueError('Invalid aggregate metric value')

def validate_metrics(metrics):
    _shape(metrics, ('host', 'cache', 'checks', 'policy') + (('system',) if type(metrics) is dict and 'system' in metrics else ()))
    if 'system' in metrics:
        from .system_metrics import validate_system
        validate_system(metrics['system'])
    host = metrics['host']; _shape(host, HOST_FIELDS)
    _number(host['uptime_s'], 10**10, integer=True)
    boot = host['boot_id']
    if boot is not None and (not isinstance(boot, str) or not re.fullmatch('[a-f0-9]{16}', boot)):
        raise ValueError('Invalid boot observation identity')
    _number(host['load_1m'], 10**6)
    for field in ('memory_used_pct', 'disk_used_pct'):
        _number(host[field], 100)
    if metrics['cache'] is not None:
        _shape(metrics['cache'], COUNTERS)
        for value in metrics['cache'].values():
            _number(value, MAX_COUNTER, integer=True)
    checks = metrics['checks']
    if type(checks) is not list or len(checks) > 6:
        raise ValueError('Too many diagnostic probes')
    seen = set()
    for check in checks:
        _shape(check, ('target', 'transport', 'qtype', 'rcode', 'elapsed_ms', 'outcome'))
        identity = (check['target'], check['transport'], check['qtype'])
        if (check['target'] not in ('local', 'upstream') or check['transport'] not in ('udp', 'tcp')
                or check['qtype'] not in ('A', 'AAAA') or identity in seen
                or check['target'] == 'upstream' and check['qtype'] != 'A'):
            raise ValueError('Invalid or duplicate diagnostic probe')
        seen.add(identity)
        if check['outcome'] not in ('response', 'timeout', 'error'):
            raise ValueError('Invalid probe outcome')
        _number(check['elapsed_ms'], 60000)
        if check['elapsed_ms'] is None:
            raise ValueError('Probe duration required')
        _number(check['rcode'], 15, integer=True)
        if (check['rcode'] is None) != (check['outcome'] != 'response'):
            raise ValueError('Probe response and outcome disagree')
    policy = metrics['policy']; _shape(policy, ('valid_until', 'active_blocks'))
    if policy['valid_until'] is not None:
        timestamp(policy['valid_until'], 'metric policy expiry')
    _number(policy['active_blocks'], 100000, integer=True)
    return metrics

def collect_host(*, proc=Path('/proc'), disk=Path('/var/lib')):
    """Fixed local paths only. No hostname, stable hardware ID or process list."""
    values = dict.fromkeys(HOST_FIELDS)
    try:
        values['uptime_s'] = int(float((proc/'uptime').read_text()[:128].split()[0]))
    except (OSError, ValueError, IndexError):
        pass
    try:
        raw = (proc/'sys/kernel/random/boot_id').read_text()[:64].strip()
        if re.fullmatch(r'[0-9a-f-]{36}', raw):
            values['boot_id'] = hashlib.sha256(raw.encode()).hexdigest()[:16]
    except OSError:
        pass
    try:
        values['load_1m'] = round(float((proc/'loadavg').read_text()[:256].split()[0]), 3)
    except (OSError, ValueError, IndexError):
        pass
    try:
        memory = {}
        for line in (proc/'meminfo').read_text().splitlines()[:100]:
            key, val = line.split(':', 1)
            if key in ('MemTotal', 'MemAvailable'):
                memory[key] = int(val.split()[0])
        if 0 <= memory['MemAvailable'] <= memory['MemTotal'] and memory['MemTotal'] > 0:
            values['memory_used_pct'] = round(100 * (1-memory['MemAvailable']/memory['MemTotal']), 2)
    except (OSError, ValueError, KeyError, IndexError):
        pass
    try:
        stat = os.statvfs(disk)
        if stat.f_blocks > 0:
            values['disk_used_pct'] = round(100*(1-stat.f_bavail/stat.f_blocks), 2)
    except OSError:
        pass
    # Missing/unavailable metrics remain null, never a fictitious zero.
    for field, maximum in [('uptime_s', 10**10), ('load_1m', 10**6),
                           ('memory_used_pct', 100), ('disk_used_pct', 100)]:
        try:
            _number(values[field], maximum, integer=field == 'uptime_s')
        except ValueError:
            values[field] = None
    return values

def read_counter_response(packet, ident, question, name):
    """Only a matching single decimal CHAOS TXT answer can become a counter."""
    if len(packet) < 12 or len(packet) > 512:
        raise ValueError('Invalid counter response length')
    rid, flags, qd, an, ns, ar = struct.unpack('!HHHHHH', packet[:12])
    if rid != ident or not flags & 0x8000 or flags & 0x7a0f or qd != 1 or an != 1:
        raise ValueError('Invalid counter response header')
    if packet[12:12+len(question)] != question:
        raise ValueError('Counter question mismatch')
    owner, offset = _dns_name(packet, 12+len(question))
    if offset+10 > len(packet):
        raise ValueError('Truncated counter answer')
    typ, cls, _, length = struct.unpack('!HHIH', packet[offset:offset+10])
    raw = packet[offset+10:offset+10+length]
    if (owner != name or typ != 16 or cls != 3 or not 2 <= length <= 18
            or len(raw) != length or raw[0] != len(raw)-1
            or re.fullmatch(rb'[0-9]{1,16}', raw[1:]) is None):
        raise ValueError('Invalid decimal CHAOS TXT record')
    value = int(raw[1:])
    if value > MAX_COUNTER:
        raise ValueError('Counter exceeds exact numeric range')
    return value

def query_counter(address, field, *, timeout=.15):
    if field not in COUNTERS:
        raise ValueError('Counter name not allowlisted')
    name = ('cachesize' if field == 'size' else field) + '.bind'
    question = b''.join(bytes([len(x)])+x for x in name.encode().split(b'.'))
    question += b'\0' + struct.pack('!HH', 16, 3)
    ident = secrets.randbits(16)
    query = struct.pack('!HHHHHH', ident, 0, 1, 0, 0, 0)+question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout); sock.connect((address, 53)); sock.send(query)
        response = sock.recv(513)
    return read_counter_response(response, ident, question, name)

def collect_metrics(address, *, cache_enabled=False, counter_reader=None, interface=None, quality_probes=False, upstream=None):
    from .system_metrics import collect_system, collect_quality
    result = blank_metrics(extended=True); result['host'] = collect_host()
    result['system'] = collect_system(interface=interface)
    if quality_probes:
        collect_quality(result['system'], address, upstream)
    if cache_enabled:
        result['cache'] = dict.fromkeys(COUNTERS)
        reader = counter_reader or query_counter
        for name in COUNTERS:
            try:
                value = reader(address, name)
                _number(value, MAX_COUNTER, integer=True)
                result['cache'][name] = value
            except (OSError, RuntimeError, ValueError):
                pass
    return validate_metrics(result)
