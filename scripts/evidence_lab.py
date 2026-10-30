#!/usr/bin/env python3
"""Non-root, loopback-only signed-delivery/DNS evidence lab; NOT an installer.

Real TLS, Ed25519, policy parser, Agent and dnsmasq are connected here. The
adapter calls Agent directly: root publish/attest, systemd, nftables, browser
caches and real threat detection are deliberately NOT certified by this lab.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
for source in ('apps/dns-agent/src', 'apps/policy-sync/src'):
    sys.path.insert(0, str(ROOT / source))


def parse_reply(raw: str, returncode: int, qtype: str) -> dict:
    status = re.search(r'\bstatus: ([A-Z]+),', raw)
    records = [line.split() for line in raw.splitlines()
               if line and not line.startswith(';') and len(line.split()) >= 5
               and line.split()[2] == 'IN']
    # Preserve owners and CNAME targets: a matching address from an unrelated
    # answer is not evidence that the requested QNAME resolved correctly.
    answers = [{'owner': r[0].lower().rstrip('.'), 'type': r[3],
                'data': r[4].lower().rstrip('.')} for r in records]
    return {'returncode': returncode, 'rcode': status[1] if status else None,
            'qtype': qtype, 'answers': answers,
            'addresses': sorted({r['data'] for r in answers if r['type'] == qtype}),
            'answer_records': len(records), 'raw': raw}


def matches(reply: dict, rcode: str, addresses: list[str], requested_name: str) -> bool:
    if (reply['returncode'] != 0 or reply['rcode'] != rcode
            or reply['addresses'] != sorted(addresses)):
        return False
    if rcode == 'NXDOMAIN':
        return reply['answer_records'] == 0
    reachable = {requested_name.lower().rstrip('.')}
    # Only follow CNAME edges rooted at the query name; unrelated answers
    # (even those containing the same expected IP) must not validate a query.
    for _ in range(len(reply['answers'])):
        expanded = reachable | {r['data'] for r in reply['answers']
                                if r['type'] == 'CNAME' and r['owner'] in reachable}
        if expanded == reachable:
            break
        reachable = expanded
    address_records = [r for r in reply['answers'] if r['type'] == reply['qtype']]
    return bool(address_records) and all(r['owner'] in reachable for r in address_records)


def summarize(rows: list[dict]) -> dict:
    successful = [r for r in rows if r.get('ok') is True]
    values = sorted(float(r['elapsed_ms']) for r in successful)
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('invalid measured duration')
    def quantile(p):
        return values[max(0, math.ceil(len(values) * p) - 1)] if values else None
    return {'attempted': len(rows), 'matched': len(successful),
            'failed': len(rows) - len(successful),
            'match_rate': len(successful) / len(rows) if rows else None,
            'successful_query_ms_p50': quantile(.5),
            'successful_query_ms_p95': quantile(.95),
            'successful_query_ms_max': max(values) if values else None,
            'latency_population': 'successful fixture queries only; failures remain in denominator'}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def query(dig: str, port: int, name: str, kind: str, tcp: bool) -> dict:
    cmd = [dig, '@127.0.0.1', '-p', str(port), name, kind,
           '+time=1', '+tries=1', '+noall', '+comments', '+answer']
    if tcp:
        cmd.append('+tcp')
    start = time.perf_counter_ns()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
        reply = parse_reply(result.stdout + result.stderr, result.returncode, kind)
    except subprocess.TimeoutExpired:
        reply = parse_reply('dig subprocess deadline exceeded', 124, kind)
    reply['elapsed_ms'] = (time.perf_counter_ns() - start) / 1e6
    return reply


@contextmanager
def tls_feed(folder: Path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ALEPH loopback lab')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    ca, pem = folder / 'lab-ca.pem', folder / 'lab-tls-key.pem'
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                     serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    pem.chmod(0o600)
    feed = {'body': b''}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/policy.json':
                self.send_error(404)
                return
            data = feed['body']
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, pem)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield feed, f'https://127.0.0.1:{server.server_port}/policy.json', ca
    finally:
        server.shutdown()
        thread.join(3)
        server.server_close()


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def provenance() -> dict:
    files = [Path(__file__), *sorted((ROOT / 'apps/dns-agent/src').rglob('*.py')),
             *sorted((ROOT / 'apps/policy-sync/src').rglob('*.py'))]
    def git(*args):
        result = subprocess.run(['git', '-C', str(ROOT), *args],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    return {'commit': git('rev-parse', 'HEAD'), 'worktree_changes': git('status', '--porcelain'),
            'python': platform.python_version(), 'platform': platform.platform(),
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in files}}


def run_lab(rounds: int, report: dict) -> None:
    if os.geteuid() == 0:
        raise RuntimeError('run as a non-root user; this lab never changes system DNS')
    binary, dig = shutil.which('dnsmasq'), shutil.which('dig')
    if not binary or not dig:
        raise RuntimeError('dnsmasq-base and dnsutils are required; missing tools are not a pass')
    # DnsmasqRuntime starts python -m dns_agent._child in a new interpreter.
    # sys.path alone is not inherited by that child; pin its checkout explicitly.
    os.environ['PYTHONPATH'] = os.pathsep.join(str(ROOT / p) for p in
        ('apps/dns-agent/src', 'apps/policy-sync/src'))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy, verify_envelope, SnapshotError
    from aleph_policy_sync.sync import fetch_once, SyncError
    from dns_agent.runtime import DnsmasqRuntime
    from dns_agent.transaction import Agent, Store
    report['provenance'] = provenance()
    report['provenance']['dnsmasq'] = subprocess.check_output(
        [binary, '--version'], text=True, timeout=5).splitlines()[0]
    names = {'blocked.test': '20', 'child.blocked.test': '21',
             'other-blocked.test': '22', 'good.test': '30', 'alias.test': '20'}
    with tempfile.TemporaryDirectory(prefix='aleph-evidence-') as temp, ExitStack() as stack:
        folder = Path(temp)
        upstream_port, port = free_port(), free_port()
        while upstream_port == port:
            port = free_port()
        config = (f'port={upstream_port}\nlisten-address=127.0.0.1\nbind-interfaces\n'
                  'no-resolv\nno-hosts\ncache-size=0\nlocal=/test/\n' + ''.join(
                  f'host-record={name},192.0.2.{suffix},2001:db8::{suffix}\n'
                  for name, suffix in names.items() if name != 'alias.test') +
                  'cname=alias.test,blocked.test\n')
        path = folder / 'upstream.conf'
        path.write_text(config)
        upstream = subprocess.Popen([binary, '--no-daemon', '--pid-file', '--log-facility=-',
                                     '--conf-file=' + str(path)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stack.callback(stop_process, upstream)
        for _ in range(40):
            if upstream.poll() is not None:
                raise RuntimeError('controlled upstream failed to start')
            if matches(query(dig, upstream_port, 'good.test', 'A', False), 'NOERROR', ['192.0.2.30'], 'good.test'):
                break
            time.sleep(.05)
        else:
            raise RuntimeError('controlled upstream not ready')
        store = stack.enter_context(Store(folder / 'state'))
        runtime = DnsmasqRuntime(binary, port)
        stack.callback(runtime.stop)
        agent = Agent(store, runtime, port=port, upstream='127.0.0.1', upstream_port=upstream_port)
        trust = folder / 'trust'
        trust.mkdir(mode=0o700)
        key = Ed25519PrivateKey.generate()
        (trust / (public_key_id(key.public_key()) + '.pem')).write_bytes(
            key.public_key().public_bytes(serialization.Encoding.PEM,
                                          serialization.PublicFormat.SubjectPublicKeyInfo))
        inbox = folder / 'inbox'
        feed, url, ca = stack.enter_context(tls_feed(folder))
        sequence = 0
        for trial in range(rounds):
            for phase in ('upstream-control', 'baseline', 'blocked', 'withdrawn'):
                boundary_start = time.perf_counter_ns()
                policy_hash = None
                if phase != 'upstream-control':
                    now = datetime.now(timezone.utc)
                    end = (now + timedelta(minutes=5)).isoformat()
                    rules = ([{'domain': 'blocked.test', 'decision': 'BLOCK', 'scope': 'SUBTREE',
                               'approved': True, 'expires_at': end, 'evidence': 'synthetic lab only'}]
                             if phase == 'blocked' else [])
                    policy = {'issued_at': now.isoformat(), 'expires_at': end, 'rules': rules}
                    sequence += 1
                    envelope = sign_policy(canonical(policy), key, target='evidence-lab',
                                           sequence=sequence, signed_at=now, confirm_empty=not rules)
                    feed['body'] = canonical(envelope)
                    fetch_once(url=url, device='evidence-lab', trust_dir=trust,
                               inbox_dir=inbox, ca_file=ca)
                    payload, parsed = verify_envelope((inbox / 'current.json').read_bytes(),
                                                       expected_device='evidence-lab', trust_dir=trust)
                    agent.cycle(canonical(payload['policy']))
                    policy_hash = parsed.digest
                transition = {'trial': trial, 'phase': phase, 'policy_sha256': policy_hash,
                              'sequence': sequence, 'server_ready_ms': (time.perf_counter_ns() - boundary_start) / 1e6,
                              'timing_boundary': 'before signing to Agent return; no timer scheduling or root publish'}
                report['transitions'].append(transition)
                for name, suffix in names.items():
                    blocked = phase == 'blocked' and name in ('blocked.test', 'child.blocked.test')
                    for kind in ('A', 'AAAA'):
                        for tcp in (False, True):
                            expected = [] if blocked else [f'192.0.2.{suffix}' if kind == 'A' else f'2001:db8::{suffix}']
                            code = 'NXDOMAIN' if blocked else 'NOERROR'
                            reply = query(dig, upstream_port if phase == 'upstream-control' else port, name, kind, tcp)
                            report['observations'].append({**reply, 'trial': trial, 'phase': phase,
                                'name': name, 'qtype': kind, 'transport': 'TCP' if tcp else 'UDP',
                                'expected_rcode': code, 'expected_addresses': expected,
                                'ok': matches(reply, code, expected, name),
                                'interpretation': 'known CNAME gap' if name == 'alias.test' and phase == 'blocked'
                                    else 'normal child affected by SUBTREE' if name == 'child.blocked.test' and blocked
                                    else 'fixture conformance; not threat truth'})
        # Corrupt a signed body after the final withdrawal: it must not reach the adapter.
        previous = (inbox / 'current.json').read_bytes()
        corrupted = json.loads(feed['body'])
        corrupted['payload']['sequence'] += 1
        feed['body'] = canonical(corrupted)
        rejected = False
        try:
            fetch_once(url=url, device='evidence-lab', trust_dir=trust, inbox_dir=inbox, ca_file=ca)
        except (SnapshotError, SyncError):
            rejected = True
        report['fault_checks'].append({'case': 'tampered signed release',
            'ok': rejected and (inbox / 'current.json').read_bytes() == previous,
            'scope': 'download rejected; last verified inbox retained; no root publisher invoked'})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--output', type=Path, help='new JSON file; existing files are never overwritten')
    args = parser.parse_args(argv)
    if not 1 <= args.rounds <= 100:
        parser.error('--rounds must be between 1 and 100')
    report = {'schema': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'synthetic non-root loopback TLS -> verified snapshot -> Agent -> dnsmasq',
              'not_measured': ['root publish/attest', 'systemd/nftables/reboot', 'real LAN/IPv6 transport',
                               'client cache recovery', 'continuous availability', 'browser incremental protection',
                               'independent threat labels', 'comparative BIND RPZ performance', 'human appeal process'],
              'observations': [], 'transitions': [], 'fault_checks': []}
    stream = args.output.open('x', encoding='utf-8') if args.output else sys.stdout
    try:
        try:
            run_lab(args.rounds, report)
        except Exception as exc:
            report['error'] = f'{type(exc).__name__}: {exc}'
        report['summary'] = summarize(report['observations'])
        report['passed'] = ('error' not in report and report['summary']['attempted'] == args.rounds * 80
                            and report['summary']['failed'] == 0 and len(report['fault_checks']) == 1
                            and all(x['ok'] for x in report['fault_checks']))
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    finally:
        if args.output:
            stream.close()
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
