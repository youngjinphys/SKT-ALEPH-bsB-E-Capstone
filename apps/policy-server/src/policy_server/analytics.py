"""Bounded, privacy-minimized observations from already authenticated receipts.

History is trusted receiver metadata, not a new signed attestation. The current
receipt signature is always checked before returning a node's history. Hourly
points are the last observation in each hour, never fictitious hourly averages.
"""
from __future__ import annotations
from datetime import datetime, timezone
import math
from aleph_policy_sync.snapshot import timestamp
from aleph_policy_sync.metrics import blank_metrics, validate_metrics
from aleph_policy_sync.system_metrics import SYSTEM_FIELDS, blank_system, validate_system

COLUMNS = ('at', 'received_at', 'sequence', 'uptime_s', 'boot_id', 'load_1m',
           'memory_used_pct', 'disk_used_pct', 'cache_hits', 'cache_misses',
           'cache_evictions', 'cache_insertions', 'cache_size', 'udp_ms', 'tcp_ms',
           'probe_count', 'probe_errors', 'active_blocks', 'policy_valid_until', 'attestation')
LEGACY_COLUMNS = COLUMNS
RESOURCE_RATES = ('cpu_used_pct','rx_bytes_per_s','tx_bytes_per_s','nic_errors_per_s','nic_drops_per_s')
COLUMNS = COLUMNS + SYSTEM_FIELDS + RESOURCE_RATES
RECENT_LIMIT = 48
HOURLY_LIMIT = 24
MAX_RECEIPT_BYTES = 131072
DAY_MS = 86400000

def _ms(value):
    return int(timestamp(value, 'observation time').timestamp()*1000)

def _history(value):
    if value is None:
        return {'format': 2, 'recent': [], 'hourly': []}
    if (type(value) is not dict or set(value) != {'format', 'recent', 'hourly'}
            or type(value['format']) is not int or value['format'] not in (1, 2)):
        raise ValueError('Invalid observation history')
    normalized = {'format': 2, 'recent': [], 'hourly': []}
    for key, limit in [('recent', RECENT_LIMIT), ('hourly', HOURLY_LIMIT)]:
        if type(value[key]) is not list or len(value[key]) > limit:
            raise ValueError('Observation history exceeds bound')
        previous = None
        for raw in value[key]:
            expected = len(LEGACY_COLUMNS) if value['format'] == 1 else len(COLUMNS)
            if type(raw) is not list or len(raw) != expected:
                raise ValueError('Invalid history row')
            row = list(raw) + ([None]*(len(SYSTEM_FIELDS)+len(RESOURCE_RATES)) if value['format'] == 1 else [])
            for i, v in enumerate(row[:len(LEGACY_COLUMNS)]):
                if i == 4:
                    import re
                    if v is not None and (not isinstance(v, str) or not re.fullmatch('[a-f0-9]{16}', v)):
                        raise ValueError('Invalid history boot ID')
                elif i == 19:
                    if v not in ('ATTESTED', 'FAILED', 'NO_POLICY', 'EXPIRED'):
                        raise ValueError('Invalid history attestation')
                elif v is not None and (type(v) not in (int, float) or not 0 <= v <= 2**53-1 or not math.isfinite(v)):
                    raise ValueError('Invalid history number')
            if (any(type(row[i]) is not int for i in (0, 1, 2, 15, 16))
                    or row[16] > row[15] or not 1 <= row[2] <= 2**53-1
                    or previous is not None and row[2] <= previous):
                raise ValueError('Invalid history counts/time')
            for index in (6,7):
                if row[index] is not None and row[index]>100:
                    raise ValueError('Invalid resource percentage')
            validate_system(dict(zip(SYSTEM_FIELDS,row[len(LEGACY_COLUMNS):len(LEGACY_COLUMNS)+len(SYSTEM_FIELDS)])))
            for rate,rate_value in zip(RESOURCE_RATES,row[-len(RESOURCE_RATES):]):
                if rate_value is not None and (type(rate_value) not in (int,float) or not math.isfinite(rate_value)
                        or not 0<=rate_value<=(100 if rate=='cpu_used_pct' else 2**53-1)):
                    raise ValueError('Invalid retained resource rate')
            previous = row[2]
            normalized[key].append(row)
    return normalized

def _sample(payload, received):
    metrics = payload.get('metrics') or blank_metrics()
    validate_metrics(metrics)
    host = metrics['host']; cache = metrics['cache'] or {}
    checks = [c for c in metrics['checks'] if c['target'] == 'local']
    def latency(protocol):
        values = [c['elapsed_ms'] for c in checks if c['transport'] == protocol and c['outcome'] == 'response']
        return round(sum(values)/len(values), 3) if values else None
    expiry = metrics['policy']['valid_until']
    return [_ms(payload['reported_at']), int(received.timestamp()*1000), payload['report_sequence'],
            host['uptime_s'], host['boot_id'], host['load_1m'], host['memory_used_pct'], host['disk_used_pct'],
            *[cache.get(k) for k in ('hits', 'misses', 'evictions', 'insertions', 'size')],
            latency('udp'), latency('tcp'), len(checks),
            sum(c['outcome'] != 'response' or c['rcode'] != 3 for c in checks),
            metrics['policy']['active_blocks'], _ms(expiry) if expiry else None, payload['attestation'],
            *[metrics.get('system', blank_system())[key] for key in SYSTEM_FIELDS],
            *[None for _ in RESOURCE_RATES]]

def _resource_rates(row, before):
    item=dict(zip(COLUMNS,row))
    if before is None:
        return
    previous=dict(zip(COLUMNS,before)); instant=item['at']-previous['at']
    if not (0<instant<=150000 and 0<item['received_at']-previous['received_at']<=150000
            and item['boot_id'] is not None and item['boot_id']==previous['boot_id']
            and item['uptime_s'] is not None and previous['uptime_s'] is not None
            and item['uptime_s']>previous['uptime_s']):
        return
    before=previous
    elapsed = item['uptime_s']-before['uptime_s']
    cpu_keys = ('cpu_total_ticks','cpu_idle_ticks')
    if (item['cpu_count'] is not None and item['cpu_count'] == before['cpu_count']
            and all(item[k] is not None and before[k] is not None for k in cpu_keys)):
        total = item['cpu_total_ticks']-before['cpu_total_ticks']
        idle = item['cpu_idle_ticks']-before['cpu_idle_ticks']
        if total>0 and 0<=idle<=total:
            item['cpu_used_pct']=round(100*(1-idle/total),3)
    if (item['interface'] is not None and item['interface']==before['interface']
            and item['ifindex'] is not None and item['ifindex']==before['ifindex']):
        net = ('rx_bytes','tx_bytes','rx_errors','tx_errors','rx_dropped','tx_dropped')
        if all(item[k] is not None and before[k] is not None and item[k]>=before[k] for k in net):
            for key in ('rx_bytes','tx_bytes'):
                item[key+'_per_s']=round((item[key]-before[key])/elapsed,3)
            item['nic_errors_per_s']=round(sum(item[k]-before[k] for k in ('rx_errors','tx_errors'))/elapsed,6)
            item['nic_drops_per_s']=round(sum(item[k]-before[k] for k in ('rx_dropped','tx_dropped'))/elapsed,6)
    for key in RESOURCE_RATES:
        row[COLUMNS.index(key)]=item[key]

def append_history(history, payload, received):
    current = _history(history)
    row = _sample(payload, received)
    cutoff = row[1] - DAY_MS
    recent = [list(r) for r in current['recent'] if r[1] >= cutoff]
    if recent and row[2] <= recent[-1][2]:
        if row[2] == recent[-1][2]:
            return current  # Retry is never an extra sample or a fresher timestamp.
        raise ValueError('Out-of-order history sequence')
    _resource_rates(row,recent[-1] if recent else None)
    recent.append(row)
    hourly = {r[1]//3600000: list(r) for r in current['hourly'] if r[1] >= cutoff}
    hourly[row[1]//3600000] = row
    return {'format': 2, 'recent': recent[-RECENT_LIMIT:],
            'hourly': [hourly[k] for k in sorted(hourly)[-HOURLY_LIMIT:]]}

def history_points(history, now=None):
    h = _history(history)
    instant = int((now or datetime.now(timezone.utc)).timestamp()*1000)
    rows = {r[2]: (r, True) for r in h['hourly']}
    rows.update({r[2]: (r, False) for r in h['recent']})
    selected = sorted((v for v in rows.values() if instant-DAY_MS <= v[0][1] <= instant+60000), key=lambda v: v[0][1])
    points = []
    for raw, coarse in selected:
        item = dict(zip(COLUMNS, raw)); item['hourly_sample'] = coarse
        item.update(cache_lookups_per_s=None, cache_hit_pct=None, cache_evictions_per_s=None,
                    report_delay_s=round((raw[1]-raw[0])/1000, 3), gap=True)
        item['dns_failure_pct']=None
        if item['dns_attempts']:
            item['dns_failure_pct'] = round(100*item['dns_failures']/item['dns_attempts'],3)
        if points:
            before = points[-1]
            dt = (item['at']-before['at'])/1000
            receive_dt = (item['received_at']-before['received_at'])/1000
            item['gap'] = not (0 < dt <= 150 and 0 < receive_dt <= 150)
            same_boot = item['boot_id'] is not None and item['boot_id'] == before['boot_id']
            same_run = (same_boot and item['uptime_s'] is not None and before['uptime_s'] is not None
                        and item['uptime_s'] > before['uptime_s'])
            if same_run and not item['gap']:
                keys = ('cache_hits', 'cache_misses', 'cache_evictions', 'cache_insertions')
                if all(item[k] is not None and before[k] is not None and item[k] >= before[k] for k in keys):
                    hits = item['cache_hits']-before['cache_hits']; misses = item['cache_misses']-before['cache_misses']
                    elapsed = item['uptime_s']-before['uptime_s']
                    item['cache_lookups_per_s'] = round((hits+misses)/elapsed, 6)
                    if hits+misses:
                        item['cache_hit_pct'] = round(100*hits/(hits+misses), 3)
                    item['cache_evictions_per_s'] = round((item['cache_evictions']-before['cache_evictions'])/elapsed, 6)
        points.append(item)
    return points
