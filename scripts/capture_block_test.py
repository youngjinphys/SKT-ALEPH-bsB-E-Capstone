#!/usr/bin/env python3
"""Capture an isolated block.test DNS experiment; never touch system DNS.

Run from the repository root as an unprivileged user:
  python3 -B scripts/capture_block_test.py --output /tmp/block-test-evidence.json
Requires local dnsmasq and dig. The output is created exclusively, not overwritten.
"""
import argparse
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'apps/dns-agent/src'
sys.dont_write_bytecode = True
sys.path.insert(0, str(PACKAGE))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTHONPATH'] = str(PACKAGE)
from dns_agent.policy import utcnow
from dns_agent.runtime import DnsmasqRuntime
from dns_agent.transaction import Agent, Store


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    files = sorted((PACKAGE / 'dns_agent').glob('*.py')) + [Path(__file__).resolve()]
    return {str(p.relative_to(ROOT)): digest(p) for p in files}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stamp():
    return utcnow().isoformat()


def capture(output, source_baseline=None, read_only_snapshot=False):
    if os.geteuid() == 0:
        raise RuntimeError('run the isolated experiment as an unprivileged user')
    dnsmasq, dig = shutil.which('dnsmasq'), shutil.which('dig')
    if not dnsmasq or not dig:
        raise RuntimeError('dnsmasq and dig are required')
    source_before = source_hashes()
    if read_only_snapshot:
        if not source_baseline or not re.fullmatch(r'[0-9a-f]{40}', source_baseline):
            raise ValueError('read-only snapshot requires a 40-hex --source-baseline')
        for relative in source_before:
            path = ROOT / relative
            if path.stat().st_mode & 0o222:
                raise RuntimeError(f'snapshot source is writable: {relative}')
            parent = path.parent
            while parent.is_relative_to(ROOT):
                if parent.stat().st_mode & 0o222:
                    raise RuntimeError(f'snapshot directory is writable: {parent}')
                parent = parent.parent
        if output.resolve().is_relative_to(ROOT):
            raise ValueError('evidence must be written outside the snapshot')
        baseline = source_baseline
    else:
        baseline = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if source_baseline and source_baseline != baseline:
            raise ValueError('provided baseline does not match repository HEAD')
    started = stamp()
    with tempfile.TemporaryDirectory(prefix='aleph-block-capture-') as directory:
        root = Path(directory)
        upstream_port, dns_port = free_port(), free_port()
        while dns_port == upstream_port:
            dns_port = free_port()
        upstream_config = (f'port={upstream_port}\nlisten-address=127.0.0.1\nbind-interfaces\n'
            'no-resolv\nno-hosts\ncache-size=0\nlocal=/test/\n'
            'host-record=block.test,192.0.2.60,2001:db8::60\n')
        conf = root / 'upstream.conf'
        conf.write_text(upstream_config, encoding='utf-8')
        proc = subprocess.Popen([dnsmasq, '--no-daemon', '--pid-file', '--log-facility=-',
                                  '--conf-file='+str(conf)], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        runtime = DnsmasqRuntime(dnsmasq, dns_port)
        try:
            def query(port, kind, tcp):
                command = [dig, '@127.0.0.1', '-p', str(port), 'block.test', kind,
                           '+time=1', '+tries=1', '+noall', '+comments', '+answer']
                if tcp:
                    command.append('+tcp')
                query_started = stamp()
                result = subprocess.run(command, text=True, capture_output=True, timeout=4, check=True)
                match = re.search(r'\bstatus: ([A-Z]+)', result.stdout)
                if not match:
                    raise RuntimeError('dig response has no DNS status')
                return {'qtype':kind, 'transport':'TCP' if tcp else 'UDP',
                        'started_at':query_started, 'finished_at':stamp(),
                        'command':command, 'exit_code':result.returncode,
                        'rcode':match.group(1), 'stdout':result.stdout, 'stderr':result.stderr}
            for _ in range(40):
                if proc.poll() is not None:
                    raise RuntimeError('fixture upstream exited')
                try:
                    if query(upstream_port, 'A', False)['rcode'] == 'NOERROR':
                        break
                except (OSError, subprocess.SubprocessError, RuntimeError):
                    time.sleep(.05)
            else:
                raise RuntimeError('fixture upstream was not ready')
            upstream_queries = [query(upstream_port, kind, tcp)
                                for kind in ('A','AAAA') for tcp in (False,True)]
            phases = []
            last_issued = None
            with Store(root / 'state') as store:
                agent = Agent(store, runtime, port=dns_port, upstream='127.0.0.1', upstream_port=upstream_port)
                for name, blocked in (('before',False), ('blocked',True), ('withdrawn',False)):
                    now = utcnow().replace(microsecond=0)
                    while last_issued is not None and now <= last_issued:
                        time.sleep(.05)
                        now = utcnow().replace(microsecond=0)
                    last_issued = now
                    rules = ([{'domain':'block.test','decision':'BLOCK','scope':'SUBTREE',
                               'approved':True,'expires_at':(now+timedelta(minutes=2)).isoformat(),
                               'evidence':'isolated-controlled-fixture'}] if blocked else [])
                    policy = {'issued_at':now.isoformat(), 'expires_at':(now+timedelta(minutes=3)).isoformat(),
                              'rules':rules}
                    applied = agent.cycle(json.dumps(policy).encode(), now=now)
                    state = store.read_state()
                    records = [query(dns_port, kind, tcp) for kind in ('A','AAAA') for tcp in (False,True)]
                    expected = 'NXDOMAIN' if blocked else 'NOERROR'
                    for record in records:
                        expected_address = '192.0.2.60' if record['qtype'] == 'A' else '2001:db8::60'
                        if record['rcode'] != expected or ((expected_address in record['stdout']) != (not blocked)):
                            raise RuntimeError(f'unexpected DNS response in {name}: {record}')
                    phases.append({'name':name, 'policy':policy, 'apply_result':applied,
                                   'active_config':state['config'], 'active_config_sha256':state['config_sha256'],
                                   'queries':records})
            for record in upstream_queries:
                address = '192.0.2.60' if record['qtype']=='A' else '2001:db8::60'
                if record['rcode']!='NOERROR' or address not in record['stdout']:
                    raise RuntimeError('controlled upstream did not return its configured address')
        finally:
            runtime.stop()
            proc.terminate()
            proc.wait(timeout=3)
    source_after = source_hashes()
    if source_before != source_after:
        raise RuntimeError('source files changed during the capture')
    data = {'schema_version':1, 'scope':'isolated loopback fixture; not production DNS',
            'source_baseline_commit':baseline,
            'source_execution_mode':'read-only-permission snapshot' if read_only_snapshot else 'working tree',
            'source_hashes_before':source_before,
            'source_hashes_after':source_after,
            'source_stability_note':'snapshot mode checks read-only permission bits; its owner could still change permissions. Matching hashes do not prove absence of transient writes',
            'started_at':started, 'finished_at':stamp(), 'python':sys.version,
            'dnsmasq':{'path':dnsmasq, 'sha256':digest(Path(dnsmasq).resolve()),
                       'version':subprocess.check_output([dnsmasq,'--version'],text=True).splitlines()[0]},
            'dig':{'path':dig, 'sha256':digest(Path(dig).resolve()),
                   'version':subprocess.check_output([dig,'-v'],text=True).strip()},
            'upstream_config':upstream_config, 'upstream_queries':upstream_queries, 'phases':phases}
    with output.open('x', encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-baseline', help='40-hex commit recorded for a source snapshot')
    parser.add_argument('--read-only-snapshot', action='store_true', help='require source files and directories to have no write bits')
    args = parser.parse_args()
    capture(args.output, source_baseline=args.source_baseline, read_only_snapshot=args.read_only_snapshot)
