"""Own an unprivileged loopback dnsmasq; check actual UDP and TCP responses."""
from __future__ import annotations
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import time


def _exact(sock, count):
    chunks = bytearray()
    while len(chunks) < count:
        data = sock.recv(count - len(chunks))
        if not data:
            raise RuntimeError('short DNS TCP response')
        chunks.extend(data)
    return bytes(chunks)



def _dns_name(packet: bytes, offset: int) -> tuple[str, int]:
    """Decode a DNS owner name with bounded, backward-only compression."""
    labels = []
    end_offset = None
    seen = set()
    while True:
        if offset in seen or offset >= len(packet):
            raise RuntimeError('invalid DNS name compression')
        seen.add(offset)
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise RuntimeError('truncated DNS name pointer')
            target = ((length & 0x3F) << 8) | packet[offset + 1]
            if target >= offset:
                raise RuntimeError('forward DNS compression pointer')
            if end_offset is None:
                end_offset = offset + 2
            offset = target
            continue
        if length & 0xC0:
            raise RuntimeError('invalid DNS label type')
        offset += 1
        if length == 0:
            return '.'.join(labels).lower(), end_offset if end_offset is not None else offset
        if offset + length > len(packet):
            raise RuntimeError('truncated DNS label')
        try:
            labels.append(packet[offset:offset + length].decode('ascii'))
        except UnicodeDecodeError as exc:
            raise RuntimeError('non-ASCII DNS name') from exc
        offset += length


def dns_rcode(name: str, qtype: int, port: int, *, tcp=False, timeout=0.5,
              require_answer=False, expected_rdata=None,
              require_no_answers=False, server_ip='127.0.0.1') -> int:
    labels = name.encode('ascii').split(b'.')
    question = b''.join(bytes([len(x)]) + x for x in labels) + b'\0' + struct.pack('!HH', qtype, 1)
    ident = secrets.randbits(16)
    query = struct.pack('!HHHHHH', ident, 0x0100, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((server_ip, port))
        if tcp:
            sock.sendall(struct.pack('!H', len(query)) + query)
            length = struct.unpack('!H', _exact(sock, 2))[0]
            response = _exact(sock, length)
        else:
            sock.send(query)
            response = sock.recv(4096)
    if len(response) < 12:
        raise RuntimeError('short DNS response')
    rid, flags, qd, answers, _, _ = struct.unpack('!HHHHHH', response[:12])
    if rid != ident or not flags & 0x8000 or flags & 0x7a00 or qd != 1:
        raise RuntimeError('mismatched, truncated or invalid DNS response')
    if response[12:12+len(question)] != question:
        raise RuntimeError('DNS question mismatch')
    if require_no_answers and (flags & 15 or answers != 0):
        raise RuntimeError('intercepted DNS type leaked a non-A answer')
    if require_answer:
        if flags & 15 or answers < 1:
            raise RuntimeError('positive DNS answer required for local health check')
        offset = 12 + len(question)
        found = False
        for _ in range(answers):
            owner, offset = _dns_name(response, offset)
            if offset + 10 > len(response):
                raise RuntimeError('truncated DNS answer')
            rrtype, rrclass, _, rdlength = struct.unpack('!HHIH', response[offset:offset + 10])
            offset += 10
            if offset + rdlength > len(response):
                raise RuntimeError('truncated DNS answer data')
            rdata = response[offset:offset + rdlength]
            offset += rdlength
            expected_length = 4 if qtype == 1 else 16 if qtype == 28 else rdlength
            if (owner == name.lower() and rrtype == qtype and rrclass == 1
                    and rdlength == expected_length
                    and (expected_rdata is None or rdata == expected_rdata)):
                found = True
        if not found:
            raise RuntimeError('local health answer missing expected record')
    return flags & 15


class DnsmasqRuntime:
    def __init__(self, binary: str, port: int,
                 listen_address: str = '127.0.0.1', system_dns: bool = False,
                 http_sink_ip: str | None = None):
        resolved = shutil.which(binary)
        if resolved is None:
            raise RuntimeError('dnsmasq not installed; install dnsmasq-base in an isolated Linux VM')
        self.binary = str(Path(resolved).resolve())
        if system_dns:
            if port != 53:
                raise RuntimeError('system DNS service must bind port 53')
        elif type(port) is not int or not 1024 <= port <= 65535:
            raise RuntimeError('unprivileged lab listen port required')
        # Same strict checks as config generation; no wildcard or public listener.
        import ipaddress
        listen = ipaddress.IPv4Address(listen_address)
        if system_dns:
            ranges = [ipaddress.ip_network(n) for n in
                      ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
            if not any(listen in net for net in ranges):
                raise RuntimeError('system DNS listener must be private RFC1918')
        elif str(listen) != '127.0.0.1':
            raise RuntimeError('lab listener must be loopback')
        self.listen_address = str(listen)
        self.system_dns = system_dns
        if http_sink_ip is not None and http_sink_ip != str(listen):
            raise RuntimeError('HTTP sink must match DNS listen address')
        self.http_sink_ip = http_sink_ip
        if os.stat(self.binary).st_mode & (stat.S_ISUID | stat.S_ISGID):
            raise RuntimeError('privilege-changing dnsmasq executable is not allowed')
        try:
            capabilities = os.getxattr(self.binary, 'security.capability')
        except OSError:
            capabilities = b''
        if capabilities:
            raise RuntimeError('file capabilities are not needed for the isolated high-port runner')
        self.port = port
        self.process = None
        self._health_name = None
        self._blocked_canary = None
        self._last_probe_at = 0.0

    def validate(self, path: Path):
        result = subprocess.run([self.binary, '--test', '--conf-file='+str(path)],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode:
            raise RuntimeError('dnsmasq syntax check failed: '+result.stderr[-1500:])

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def _check_canary(self, name: str, *, tcp: bool):
        if self.http_sink_ip is None:
            for qtype in (1, 28):
                if dns_rcode(name, qtype, self.port, tcp=tcp,
                             server_ip=self.listen_address) != 3:
                    raise RuntimeError('normal block canary did not return NXDOMAIN')
            return
        sink = socket.inet_pton(socket.AF_INET, self.http_sink_ip)
        if dns_rcode(name, 1, self.port, tcp=tcp, require_answer=True,
                     expected_rdata=sink, server_ip=self.listen_address) != 0:
            raise RuntimeError('HTTP notice A canary did not resolve to the sink')
        if dns_rcode(name, 28, self.port, tcp=tcp, require_no_answers=True,
                     server_ip=self.listen_address) != 0:
            raise RuntimeError('HTTP notice AAAA canary must have no answers')

    def healthy(self) -> bool:
        """Periodically verify local DNS answers, not just process existence.

        Only local fixture answers are checked; upstream availability is separate.
        """
        if not self.alive() or self._health_name is None:
            return False
        if time.monotonic() - self._last_probe_at < 5.0:
            return True
        try:
            for tcp in (False, True):
                for qtype, family, literal in (
                    (1, socket.AF_INET, '192.0.2.1'),
                    (28, socket.AF_INET6, '2001:db8::1'),
                ):
                    expected = socket.inet_pton(family, literal)
                    if dns_rcode(self._health_name, qtype, self.port, tcp=tcp,
                                 require_answer=True, expected_rdata=expected,
                                 server_ip=self.listen_address) != 0:
                        return False
                if self._blocked_canary:
                    self._check_canary(self._blocked_canary, tcp=tcp)
        except (OSError, RuntimeError):
            return False
        self._last_probe_at = time.monotonic()
        return self.alive()

    def start(self, path: Path):
        if os.geteuid() == 0:
            raise RuntimeError('run the isolated DNS agent as an unprivileged user, not sudo')
        if self.alive():
            raise RuntimeError('owned dnsmasq already running')
        if sys.platform != 'linux':
            raise RuntimeError('Linux required for parent-death cleanup')
        content = path.read_text(encoding='utf-8')
        health = next(line.split('=',1)[1].split(',')[0]
                      for line in content.splitlines() if line.startswith('host-record='))
        blocked = [line.split('/')[1] for line in content.splitlines() if line.startswith('address=/')]
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'dns_agent._child', str(os.getpid()), self.binary,
             '--keep-in-foreground', '--pid-file', '--log-facility=-', '--conf-file='+str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        deadline = time.monotonic() + 4
        try:
            while time.monotonic() < deadline:
                if not self.alive():
                    raise RuntimeError('dnsmasq exited during startup; check port and file permissions')
                try:
                    for tcp in (False, True):
                        for qtype in (1, 28):
                            expected = socket.inet_pton(
                                socket.AF_INET if qtype == 1 else socket.AF_INET6,
                                '192.0.2.1' if qtype == 1 else '2001:db8::1')
                            if dns_rcode(health, qtype, self.port, tcp=tcp,
                                         require_answer=True, expected_rdata=expected,
                                         server_ip=self.listen_address) != 0:
                                raise RuntimeError('health query failed')
                        if blocked:
                            self._check_canary(blocked[0], tcp=tcp)
                    self._health_name = health
                    self._blocked_canary = blocked[0] if blocked else None
                    self._last_probe_at = 0.0
                    return
                except (OSError, RuntimeError):
                    time.sleep(0.05)
            raise RuntimeError('DNS health checks timed out')
        except Exception:
            self.stop()
            raise

    def stop(self):
        self._health_name = None
        self._blocked_canary = None
        self._last_probe_at = 0.0
        process, self.process = self.process, None
        if process is None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
