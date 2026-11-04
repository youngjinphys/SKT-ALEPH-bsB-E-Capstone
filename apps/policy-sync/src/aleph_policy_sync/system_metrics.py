"""Linux host counters and explicitly opted-in DNS quality probes.

Only aggregate counters are signed. No process list, client addresses, browsing
history or packet capture. CPU and link rates are derived by the receiver from
two same-boot observations, never from wall clock or invented zero baselines.
"""
from __future__ import annotations
import math
from pathlib import Path
import re
import time

SYSTEM_FIELDS = ('cpu_total_ticks', 'cpu_idle_ticks', 'cpu_count', 'interface', 'ifindex',
                 'rx_bytes', 'tx_bytes', 'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped',
                 'local_dns_udp_ms', 'local_dns_tcp_ms', 'upstream_dns_udp_ms', 'upstream_dns_tcp_ms',
                 'dns_attempts', 'dns_failures', 'probe_domain')
COUNTER_FIELDS = ('cpu_total_ticks', 'cpu_idle_ticks', 'cpu_count', 'ifindex', 'rx_bytes',
                  'tx_bytes', 'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped',
                  'dns_attempts', 'dns_failures')
LATENCY_FIELDS = ('local_dns_udp_ms', 'local_dns_tcp_ms', 'upstream_dns_udp_ms', 'upstream_dns_tcp_ms')
NET_FIELDS = ('rx_bytes', 'tx_bytes', 'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped')
MAX_COUNTER = 2**53-1
PROBE_DOMAIN = 'example.org'


def blank_system():
    return dict.fromkeys(SYSTEM_FIELDS)


def interface_name(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}', value):
        raise ValueError('Invalid explicitly configured metrics interface')
    return value


def validate_system(value):
    if type(value) is not dict or set(value) != set(SYSTEM_FIELDS):
        raise ValueError('Unexpected host resource metric fields')
    interface_name(value['interface'])
    for key in COUNTER_FIELDS:
        item=value[key]
        if item is not None and (type(item) is not int or not 0 <= item <= MAX_COUNTER):
            raise ValueError('Invalid resource counter')
    for key in LATENCY_FIELDS:
        item=value[key]
        if item is not None and (type(item) not in (int,float) or not math.isfinite(item) or not 0 <= item <= 60000):
            raise ValueError('Invalid DNS quality duration')
    total,idle=value['cpu_total_ticks'],value['cpu_idle_ticks']
    if (total is None) != (idle is None) or total is not None and idle>total:
        raise ValueError('Inconsistent CPU counters')
    if value['cpu_count'] is not None and not 1 <= value['cpu_count'] <= 65536:
        raise ValueError('Invalid logical CPU count')
    if value['interface'] is None and any(value[k] is not None for k in ('ifindex',*NET_FIELDS)):
        raise ValueError('Network counters need an explicit interface')
    if value['ifindex'] is not None and not 1 <= value['ifindex'] <= 2**31-1:
        raise ValueError('Invalid interface index')
    attempts,failures=value['dns_attempts'],value['dns_failures']
    if attempts is None:
        if failures is not None or value['probe_domain'] is not None or any(value[k] is not None for k in LATENCY_FIELDS):
            raise ValueError('DNS quality observations need sample counts')
    elif (attempts not in (2,4) or failures is None or failures>attempts
          or value['probe_domain']!=PROBE_DOMAIN
          or sum(value[k] is not None for k in LATENCY_FIELDS)!=attempts-failures
          or attempts==2 and any(value[k] is not None for k in LATENCY_FIELDS[2:])):
        raise ValueError('Inconsistent DNS quality sample counts')
    return value


def _read(path,limit=131072):
    with Path(path).open('r',encoding='ascii') as handle:
        value=handle.read(limit+1)
    if len(value)>limit:
        raise ValueError('Kernel observation exceeds size bound')
    return value


def collect_system(*,proc=Path('/proc'),net=Path('/sys/class/net'),interface=None):
    value=blank_system(); interface=interface_name(interface)
    try:
        lines=_read(proc/'stat').splitlines()
        parts=lines[0].split()
        if parts[0]!='cpu' or len(parts)<9:
            raise ValueError('CPU counter header missing')
        # guest/guest_nice are already included in user/nice; do not sum twice.
        ticks=[int(x) for x in parts[1:9]]
        if any(x<0 for x in ticks) or sum(ticks)>MAX_COUNTER:
            raise ValueError('Invalid kernel ticks')
        count=sum(bool(re.match(r'^cpu[0-9]+\s',line)) for line in lines)
        if not 1<=count<=65536:
            raise ValueError('CPU count unavailable')
        value.update(cpu_total_ticks=sum(ticks),cpu_idle_ticks=ticks[3]+ticks[4],cpu_count=count)
    except (OSError,ValueError,IndexError,UnicodeError):
        pass
    if interface:
        value['interface']=interface
        try:
            folder=net/interface
            index=int(_read(folder/'ifindex',32).strip())
            if not 1<=index<=2**31-1:
                raise ValueError('Invalid interface index')
            counters={key:int(_read(folder/'statistics'/key,32).strip()) for key in NET_FIELDS}
            if any(not 0<=x<=MAX_COUNTER for x in counters.values()):
                raise ValueError('Invalid network counter')
            # A hotplug during the multi-file read must not mix two devices.
            if int(_read(folder/'ifindex',32).strip()) != index:
                raise ValueError('Interface changed during observation')
            value.update(ifindex=index,**counters)
        except (OSError,ValueError,UnicodeError):
            pass
    return validate_system(value)


def collect_quality(value,address,upstream,*,resolver=None,clock=time.monotonic):
    """Four bounded synthetic A lookups at most, never a speed or packet-loss test."""
    from dns_agent.runtime import dns_rcode
    resolver=resolver or dns_rcode
    value.update(dns_attempts=0,dns_failures=0,probe_domain=PROBE_DOMAIN)
    for label,target in [('local',address),('upstream',upstream)]:
        if target is None:
            continue
        for tcp in (False,True):
            key=f'{label}_dns_{"tcp" if tcp else "udp"}_ms'
            value[key]=None; value['dns_attempts']+=1
            start=clock()
            try:
                code=resolver(PROBE_DOMAIN,1,53,tcp=tcp,server_ip=target,timeout=1.0,require_answer=True)
                elapsed=(clock()-start)*1000
                if code!=0 or not math.isfinite(elapsed) or not 0<=elapsed<=60000:
                    raise ValueError('No valid positive DNS response')
                value[key]=round(elapsed,3)
            except (OSError,RuntimeError,ValueError):
                value['dns_failures']+=1
    return validate_system(value)
