"""Opt-in, policy-backed *plaintext HTTP* notice service for an authorized lab.

Requires the matching DNS agent to be started with --http-notice-ip and to
have accepted a policy. Read only its committed, checksum-verified state;
never forward requests, proxy HTTPS, use request URLs for redirect targets,
or change DNS / OS networking. This is not a production TLS solution.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import sys
import threading
from typing import NamedTuple

from .policy import PolicyError, MAX_BYTES, domain_name, parse_policy
from .transaction import Store, read_regular

# The existing warning portal remains unchanged. Only this allowlist is served.
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/phishing-block.html': ('phishing-block.html', 'text/html; charset=utf-8'),
    '/phishing-warning-continue.html': ('phishing-warning-continue.html', 'text/html; charset=utf-8'),
    '/portal.css': ('portal.css', 'text/css; charset=utf-8'),
    '/portal.js': ('portal.js', 'text/javascript; charset=utf-8'),
    '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
}
CSP = ("default-src 'none'; base-uri 'none'; object-src 'none'; "
       "frame-ancestors 'none'; form-action 'none'; connect-src 'none'; "
       "script-src 'self'; style-src 'self'; img-src 'self'; font-src 'none'")
MAX_REQUEST_TARGET = 2048
MAX_HTTP_HOST = 255


class NoticeError(RuntimeError):
    """Local policy/configuration is not trustworthy enough to redirect."""


class Settings(NamedTuple):
    listen: str
    client_net: ipaddress.IPv4Network
    redirect_port: int
    portal_port: int
    state_dir: Path
    static_root: Path


def validate_settings(*, listen: str, client_cidr: str, redirect_port: int,
                      portal_port: int, state_dir: Path, static_root: Path) -> Settings:
    try:
        ip = ipaddress.IPv4Address(listen)
        network = ipaddress.IPv4Network(client_cidr, strict=True)
    except (TypeError, ValueError) as exc:
        raise NoticeError('IPv4 listen and canonical client CIDR required') from exc
    private = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if ip.is_loopback:
        if network != ipaddress.IPv4Network('127.0.0.1/32') or ip != ipaddress.IPv4Address('127.0.0.1'):
            raise NoticeError('loopback lab requires listen 127.0.0.1 and client 127.0.0.1/32')
    elif not any(ip in n and network.subnet_of(n) for n in private):
        raise NoticeError('LAN HTTP listener and clients must be private RFC1918 IPv4')
    elif network.prefixlen < 24:
        raise NoticeError('HTTP lab client access must be /24 or narrower')
    if ip not in network:
        raise NoticeError('client CIDR must include the configured listener')
    for port in (redirect_port, portal_port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise NoticeError('valid HTTP ports required')
    if redirect_port == portal_port:
        raise NoticeError('redirect and portal ports must differ')
    if not isinstance(state_dir, Path) or not isinstance(static_root, Path):
        raise NoticeError('absolute state and public asset paths required')
    if not state_dir.is_absolute() or not static_root.is_absolute():
        raise NoticeError('absolute state and public asset paths required')
    return Settings(str(ip), network, redirect_port, portal_port, state_dir, static_root)


def load_public_assets(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise NoticeError('invalid public asset directory')
    data = {}
    for route, (name, mime) in ASSETS.items():
        if route == '/':
            continue
        f = root/name
        st = f.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_size > 1024*1024:
            raise NoticeError('unsafe or oversized public asset')
        content = f.read_bytes()
        if len(content) != st.st_size:
            raise NoticeError('public asset changed during loading')
        data[route] = (content, mime)
    data['/'] = data['/index.html']
    return data


def parse_host(value: str, expected_port: int):
    """Host header can identify a policy QNAME, never a redirect destination."""
    if not isinstance(value,str) or len(value)>MAX_HTTP_HOST or value != value.strip():
        raise ValueError('invalid host')
    if not value.isascii() or '@' in value or '/' in value or '\\' in value or '[' in value:
        raise ValueError('invalid host')
    tokens = value.split(':')
    if len(tokens) > 2:
        raise ValueError('invalid host')
    if len(tokens) == 2 and tokens[1] != str(expected_port):
        raise ValueError('unexpected host port')
    # reject numeric/IP-only targets or Unicode IDN to avoid misleading displays
    return domain_name(tokens[0])


def match_subtree(name: str, domain: str) -> bool:
    return name == domain or name.endswith('.'+domain)


def read_active_routes(directory: Path, expected_ip: str, *, now: datetime | None = None):
    """Use only the exact policy accepted by DNS, and verify its active config."""
    now = now or datetime.now(timezone.utc)
    try:
        raw = read_regular(directory/'state.json', 4*MAX_BYTES)
        state = json.loads(raw)
        Store._check_snapshot(state)
        active = read_regular(directory/'active.conf', 2*MAX_BYTES).decode('utf-8')
        if active != state['config']:
            raise NoticeError('inconsistent active resolver configuration')
        policy = parse_policy(state['policy'].encode('utf-8'), now=now)
        if policy.expires_at <= now:
            return ()
        rules = tuple((r.domain,r.decision) for r in policy.rules if
                      r.approved and r.decision in ('BLOCK','WARN') and r.expires_at > now)
        expected_addresses = {f'address=/{name}/{expected_ip}' for name,_ in rules}
        expected_local = {f'local=/{name}/' for name,_ in rules}
        entries = active.splitlines()
        addresses = {s for s in entries if s.startswith('address=/')}
        locals_ = {s for s in entries if s.startswith('local=/') and s!='local=/capstone.test/'}
        if (addresses != expected_addresses or locals_ != expected_local
                or sum(entry.startswith('address=/') for entry in entries) != len(addresses)
                or sum(entry.startswith('local=/') and entry != 'local=/capstone.test/'
                       for entry in entries) != len(locals_)):
            raise NoticeError('DNS is not in matching HTTP notice mode')
        if f'listen-address={expected_ip}' not in entries:
            raise NoticeError('DNS listen/sink IP mismatch')
        if len(addresses)!=len(rules):
            raise NoticeError('duplicate or ambiguous notice records')
        return tuple(sorted(rules, key=lambda r: (-len(r[0]),r[0])))
    except (OSError, ValueError, TypeError, KeyError, PolicyError, UnicodeError, RuntimeError) as exc:
        raise NoticeError('active DNS policy is unavailable or unverified') from exc


def classify(name: str, routes):
    for domain, decision in routes:
        if match_subtree(name, domain):
            return decision
    return None


class NoticeHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 24

    def get_request(self):
        client, peer = super().get_request()
        client.settimeout(3)
        return client, peer


class QuietHandler(http.server.BaseHTTPRequestHandler):
    server_version = 'ALEPH-HTTP-Lab'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        # No query, Host, URL, client IP or cookie logs.
        pass

    def respond(self, code: int, body=b'', mime='text/plain; charset=utf-8', location=None):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',CSP)
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=(), payment=()')
        self.send_header('Connection','close')
        if location is not None:
            self.send_header('Location',location)
        if code == 405:
            self.send_header('Allow','GET, HEAD')
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        self.respond(code, b'HTTP lab request rejected.\n')

    def _preflight(self):
        try:
            address = ipaddress.ip_address(self.client_address[0])
            if address not in self.server.client_net:
                self.respond(403, b'Client is not approved for this HTTP lab.\n')
                return False
        except (TypeError, ValueError):
            self.respond(400)
            return False
        if len(self.path) > MAX_REQUEST_TARGET or '://' in self.path or not self.path.startswith('/'):
            self.respond(400)
            return False
        return True

    def _host(self):
        hosts=self.headers.get_all('Host', [])
        if len(hosts)!=1:
            raise ValueError('exactly one host required')
        return hosts[0]

    def do_GET(self):
        if not self._preflight():
            return
        self.get_route()

    do_HEAD=do_GET

    def do_POST(self):
        self.respond(405, b'Body-bearing HTTP requests are not redirected.\n')

    do_PUT=do_POST
    do_PATCH=do_POST
    do_DELETE=do_POST
    do_CONNECT=do_POST
    do_OPTIONS=do_POST


def redirect_handler(settings: Settings):
    destination = {
        'BLOCK': f'http://{settings.listen}:{settings.portal_port}/phishing-block.html',
        'WARN': f'http://{settings.listen}:{settings.portal_port}/phishing-warning-continue.html',
    }

    class Redirect(QuietHandler):
        def get_route(self):
            try:
                name=parse_host(self._host(),settings.redirect_port)
            except (ValueError,PolicyError):
                self.respond(400,b'Invalid HTTP Host.\n')
                return
            try:
                routes=read_active_routes(settings.state_dir,settings.listen)
            except NoticeError:
                self.respond(503,b'The active DNS policy could not be verified.\n')
                return
            verdict=classify(name,routes)
            if verdict in destination:
                self.respond(302,location=destination[verdict])
            else:
                # This is *not* a forward proxy. ALLOW and unknown are not touched.
                self.respond(404,b'No HTTP notice for this name.\n')

    return Redirect


def portal_handler(settings: Settings, assets):
    class Portal(QuietHandler):
        def get_route(self):
            try:
                host=self._host()
            except ValueError:
                self.respond(400)
                return
            if host != f'{settings.listen}:{settings.portal_port}':
                self.respond(421,b'Portal Host mismatch.\n')
                return
            route=self.path.split('?',1)[0]
            asset=assets.get(route)
            if asset is None:
                self.respond(404,b'Unknown public asset.\n')
                return
            data,mime=asset
            self.respond(200,data,mime)

    return Portal


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--listen-ip',required=True,help='127.0.0.1 or an assigned private IPv4')
    parser.add_argument('--client-cidr',required=True,help='operator-approved /24 or smaller client range')
    parser.add_argument('--state-dir',type=Path,required=True,help='DNS agent state directory')
    parser.add_argument('--static-dir',type=Path,required=True,help='directory of existing warning portal public files')
    parser.add_argument('--http-port',type=int,default=38080,help='80 for actual http:// host visits; 38080 for high-port lab')
    parser.add_argument('--portal-port',type=int,default=35173)
    parser.add_argument('--ack-plaintext-only',action='store_true',help='explicitly accept that HTTPS and HSTS do not redirect')
    opts=parser.parse_args(argv)
    try:
        if not opts.ack_plaintext_only:
            raise NoticeError('explicit --ack-plaintext-only required')
        if os.geteuid()==0:
            raise NoticeError('do not run the lab HTTP listeners as root; use systemd port capability for :80')
        conf=validate_settings(listen=opts.listen_ip,client_cidr=opts.client_cidr,
                               redirect_port=opts.http_port,portal_port=opts.portal_port,
                               state_dir=opts.state_dir,static_root=opts.static_dir)
        assets=load_public_assets(conf.static_root)
        shutdown=threading.Event()
        prior={}
        try:
            with ExitStack() as stack:
                p=stack.enter_context(NoticeHTTPServer((conf.listen,conf.portal_port),portal_handler(conf,assets)))
                g=stack.enter_context(NoticeHTTPServer((conf.listen,conf.redirect_port),redirect_handler(conf)))
                for server in (p,g):
                    server.client_net=conf.client_net
                    worker=threading.Thread(target=server.serve_forever,daemon=True)
                    worker.start()
                    stack.callback(worker.join,2)
                    stack.callback(server.shutdown)
                for signum in (signal.SIGINT,signal.SIGTERM):
                    prior[signum]=signal.signal(signum,lambda *_: shutdown.set())
                print(f'Lab-only HTTP notice: {conf.listen}:{conf.redirect_port}; static notice: {conf.listen}:{conf.portal_port}; no HTTPS interception or DNS changes',flush=True)
                shutdown.wait()
        finally:
            for signum,handler in prior.items():
                signal.signal(signum,handler)
        return 0
    except (NoticeError,OSError,ValueError) as exc:
        parser.exit(2,'ERROR: '+str(exc)+'\n')


if __name__=='__main__':
    raise SystemExit(main())
