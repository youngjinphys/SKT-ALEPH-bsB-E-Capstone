"""Read-only validation/render by default; 'run' explicitly starts a lab listener."""
from __future__ import annotations
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import sys
import threading
from .policy import parse_policy, render_config, utcnow, PolicyError
from .runtime import DnsmasqRuntime
from .transaction import Agent, Store, ApplyError, RecoveryError, read_regular


def example():
    now = utcnow().replace(microsecond=0)
    end = (now + timedelta(hours=1)).isoformat()
    return {'issued_at': now.isoformat(), 'expires_at': end, 'rules': [
        {'domain': domain, 'decision': decision, 'scope': 'SUBTREE', 'approved': True,
         'expires_at': end, 'evidence': 'synthetic-lab-only'}
        for domain, decision in [('blocked.test','BLOCK'), ('warn.test','WARN'), ('good.test','ALLOW')]
    ]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('example', help='print a fresh synthetic policy; no writes or DNS changes')
    for name in ('validate','render','run'):
        command = commands.add_parser(name)
        command.add_argument('policy', type=Path)

        if name in ('render','run'):
            command.add_argument('--port', type=int, default=35353)
            command.add_argument('--listen-address', default='127.0.0.1',
                                 help='loopback by default; private LAN IP only with --system-dns')
            command.add_argument('--system-dns', action='store_true',
                                 help='explicit port 53 LAN mode, requires a managed systemd service')
            command.add_argument('--upstream', required=True, help='operator-selected trusted resolver IP')
            command.add_argument('--upstream-port', type=int, default=53)
            command.add_argument('--http-sink-ip',
                                 help='OPT-IN HTTP lab: redirect approved BLOCK/WARN A records to this listener')
            command.add_argument('--ack-http-sinkhole', action='store_true',
                                 help='accept HTTPS/HSTS failure and changed WARN DNS behavior')
        if name == 'run':
            command.add_argument('--state-dir', type=Path, required=True,
                                 help='private 0700 directory owned by the current user')
            command.add_argument('--dnsmasq', default='dnsmasq')
            command.add_argument('--poll-seconds', type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        if args.command in ('render', 'run'):
            if bool(args.http_sink_ip) != bool(args.ack_http_sinkhole):
                raise PolicyError('--http-sink-ip requires --ack-http-sinkhole (and vice versa)')
        if args.command == 'example':
            print(json.dumps(example(), ensure_ascii=False, indent=2)); return 0
        if args.command in ('validate', 'render'):
            raw = read_regular(args.policy)
            policy = parse_policy(raw)
            if args.command == 'validate':
                print(json.dumps({'policy_sha256': policy.digest, 'rules': len(policy.rules),
                                  'active_blocks': len(policy.blocked(utcnow())),
                                  'expired': utcnow() >= policy.expires_at})); return 0
            config = render_config(policy.blocked(utcnow()), port=args.port,
                                   upstream=args.upstream, upstream_port=args.upstream_port,
                                   listen_address=args.listen_address,
                                   system_dns=args.system_dns,
                                   warned=policy.warned(utcnow()) if args.http_sink_ip else (),
                                   http_sink_ip=args.http_sink_ip)
            print(config, end=''); return 0
        if os.geteuid() == 0:
            raise PolicyError('do not use sudo: the lab runner requires an unprivileged account')
        if not 0.1 <= args.poll_seconds <= 10:
            raise PolicyError('poll-seconds must be between 0.1 and 10')
        runtime = DnsmasqRuntime(args.dnsmasq, args.port,
                                 listen_address=args.listen_address,
                                 system_dns=args.system_dns,
                                 http_sink_ip=args.http_sink_ip)
        stop = threading.Event()
        def request_stop(*_): stop.set()
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
        last_event = None
        with Store(args.state_dir) as store:
            agent = Agent(store, runtime, port=args.port, upstream=args.upstream,
                          upstream_port=args.upstream_port,
                          listen_address=args.listen_address, system_dns=args.system_dns,
                          http_sink_ip=args.http_sink_ip)
            try:
                while not stop.is_set():
                    try:
                        raw = read_regular(args.policy)
                    except (OSError, RuntimeError, PolicyError):
                        raw = None  # keep last reviewed policy only until its expiry
                    try:
                        event = agent.cycle(raw)
                    except ApplyError as exc:
                        if not runtime.alive(): raise
                        if not runtime.healthy():
                            raise RecoveryError('existing DNS unhealthy after rejected update') from exc
                        event = {'event':'candidate_rejected', 'reason':str(exc)}
                    if event != last_event:
                        print(json.dumps(event, ensure_ascii=False), flush=True)
                        last_event = event
                    stop.wait(args.poll_seconds)
            finally:
                runtime.stop()
        return 0
    except (PolicyError, OSError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 3 if isinstance(exc, RecoveryError) else 2

if __name__ == '__main__':
    raise SystemExit(main())
