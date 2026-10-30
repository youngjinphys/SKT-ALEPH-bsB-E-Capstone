import socket
import struct
import threading
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from dns_agent.runtime import dns_rcode, DnsmasqRuntime

class WireTests(unittest.TestCase):
    def test_periodic_health_detects_tcp_listener_failure(self):
        # Real loopback DNS packets succeed over UDP while TCP has no listener.
        # A supervisor must not report the two-transport service as healthy.
        # Reserve the TCP port without listening so another process cannot
        # accidentally make the expected connection refusal succeed.
        tcp_guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_guard.bind(('127.0.0.1', 0))
        port = tcp_guard.getsockname()[1]
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(('127.0.0.1', port))
        udp.settimeout(0.1)
        stop = threading.Event()

        def serve():
            while not stop.is_set():
                try:
                    query, peer = udp.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    return
                qtype = struct.unpack('!H', query[-4:-2])[0]
                if qtype == 1:
                    rdata = socket.inet_pton(socket.AF_INET, '192.0.2.1')
                else:
                    rdata = socket.inet_pton(socket.AF_INET6, '2001:db8::1')
                udp.sendto(self._answer_packet(query, qtype, rdata), peer)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        class Alive:
            def poll(self): return None
        try:
            runtime = DnsmasqRuntime('/bin/true', port)
            runtime.process = Alive()
            runtime._health_name = 'health-demo.capstone.test'
            self.assertFalse(runtime.healthy())
        finally:
            stop.set()
            thread.join(timeout=1)
            udp.close()
            tcp_guard.close()

    def test_periodic_health_probe_checks_local_answers_and_block_canary(self):
        # No operating-system DNS service is needed for these wire-level assertions.
        class Alive:
            def poll(self): return None

        runtime = DnsmasqRuntime('/bin/true', 35353)
        runtime.process = Alive()
        runtime._health_name = 'health-demo.capstone.test'
        runtime._blocked_canary = 'blocked.test'
        runtime._last_probe_at = 0
        with patch('dns_agent.runtime.dns_rcode', side_effect=[0, 0, 3, 3, 0, 0, 3, 3]) as query:
            self.assertTrue(runtime.healthy())
            self.assertEqual(query.call_count, 8)
        # Identical healthy process: skip redundant probes within five seconds.
        with patch('dns_agent.runtime.dns_rcode') as query:
            self.assertTrue(runtime.healthy())
            query.assert_not_called()
        runtime._last_probe_at = 0
        with patch('dns_agent.runtime.dns_rcode', side_effect=[0, 0, 0]):
            self.assertFalse(runtime.healthy())
        runtime._last_probe_at = 0
        with patch('dns_agent.runtime.dns_rcode', side_effect=RuntimeError('no DNS answer')):
            self.assertFalse(runtime.healthy())

    def test_http_notice_health_requires_sink_a_and_no_aaaa_answers(self):
        class Alive:
            def poll(self): return None
        runtime=DnsmasqRuntime('/bin/true',35353,http_sink_ip='127.0.0.1')
        runtime.process=Alive()
        runtime._health_name='health-test.capstone.test'
        runtime._blocked_canary='warn.test'
        runtime._last_probe_at=0
        with patch('dns_agent.runtime.dns_rcode',side_effect=[0,0,0,0,0,0,0,0]) as request:
            self.assertTrue(runtime.healthy())
            self.assertEqual(request.call_count,8)
            self.assertTrue(any(k.kwargs.get('require_no_answers') for k in request.call_args_list))
            self.assertTrue(any(k.kwargs.get('expected_rdata') == b'\x7f\x00\x00\x01'
                                for k in request.call_args_list))
        runtime._last_probe_at=0
        with patch('dns_agent.runtime.dns_rcode',side_effect=[0,0,0,3]):
            self.assertFalse(runtime.healthy())
        with self.assertRaisesRegex(RuntimeError,'must match'):
            DnsmasqRuntime('/bin/true',35353,http_sink_ip='192.168.7.69')

    def test_privileged_binary_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'fake-dnsmasq';binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o4755)
            with self.assertRaisesRegex(RuntimeError,'privilege-changing'):
                DnsmasqRuntime(str(binary),35353)
    def test_system_runtime_validates_privileged_port_and_private_ip(self):
        with self.assertRaises(RuntimeError):
            DnsmasqRuntime('/bin/true', 53)
        self.assertEqual(DnsmasqRuntime('/bin/true', 53, '192.168.44.10',
                                        system_dns=True).listen_address, '192.168.44.10')
        with self.assertRaises(RuntimeError):
            DnsmasqRuntime('/bin/true', 53, '8.8.8.8', system_dns=True)

    def test_low_port_is_rejected(self):
        with self.assertRaises(RuntimeError): DnsmasqRuntime('/bin/true',53)
    def respond(self, mutate):
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.bind(('127.0.0.1',0))
        def run():
            try:
                query,peer=sock.recvfrom(1024)
                sock.sendto(mutate(query),peer)
            finally: sock.close()
        thread=threading.Thread(target=run,daemon=True); thread.start()
        return sock.getsockname()[1],thread
    def test_positive_and_nxdomain(self):
        for rcode in (0,3):
            port,t=self.respond(lambda q: q[:2]+struct.pack('!H',0x8180|rcode)+q[4:])
            self.assertEqual(dns_rcode('health.capstone.test',1,port),rcode);t.join()
    def test_empty_noerror_is_not_a_health_answer(self):
        port,t=self.respond(lambda q:q[:2]+b'\x81\x80'+q[4:])
        with self.assertRaises(RuntimeError):
            dns_rcode('health.capstone.test',1,port,require_answer=True)
        t.join()
    @staticmethod
    def _answer_packet(query, qtype=1, rdata=None, owner=b'\xc0\x0c'):
        if rdata is None:
            rdata = b'\xc0\x00\x02\x01' if qtype == 1 else socket.inet_pton(socket.AF_INET6, '2001:db8::1')
        header = query[:2] + struct.pack('!HHHHH', 0x8180, 1, 1, 0, 0)
        answer = owner + struct.pack('!HHIH', qtype, 1, 0, len(rdata)) + rdata
        return header + query[12:] + answer

    def test_health_response_accepts_valid_a_and_aaaa_records(self):
        for qtype, rdata in [(1, b'\xc0\x00\x02\x01'),
                             (28, socket.inet_pton(socket.AF_INET6, '2001:db8::1'))]:
            port, thread = self.respond(lambda q, t=qtype, d=rdata:
                                        self._answer_packet(q, t, d))
            self.assertEqual(dns_rcode('health.capstone.test', qtype, port,
                                       require_answer=True, expected_rdata=rdata), 0)
            thread.join()

    def test_health_response_accepts_fragmented_tcp_frame(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve():
            conn, _ = listener.accept()
            with conn:
                length = struct.unpack('!H', conn.recv(2, socket.MSG_WAITALL))[0]
                query = conn.recv(length, socket.MSG_WAITALL)
                response = self._answer_packet(query)
                framed = struct.pack('!H', len(response)) + response
                for byte in framed:
                    conn.sendall(bytes([byte]))
            listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.assertEqual(dns_rcode('health.capstone.test', 1, port, tcp=True,
                                   require_answer=True,
                                   expected_rdata=b'\xc0\x00\x02\x01'), 0)
        thread.join(timeout=1)

    def test_health_response_rejects_truncated_answer_body(self):
        port, thread = self.respond(lambda q: self._answer_packet(q)[:-1])
        with self.assertRaisesRegex(RuntimeError, 'truncated DNS answer'):
            dns_rcode('health.capstone.test', 1, port, require_answer=True)
        thread.join()

    def test_health_response_rejects_wrong_record_and_ip(self):
        cases = (
            lambda q: self._answer_packet(q, qtype=28),
            lambda q: self._answer_packet(q, rdata=b'\x7f\x00\x00\x01'),
            lambda q: self._answer_packet(q, owner=b'\x03bad\x00'),
            lambda q: (q[:2] + struct.pack('!HHHHH', 0x8180, 1, 1, 0, 0)
                       + q[12:] + b'!'),
        )
        for build in cases:
            port, thread = self.respond(build)
            with self.assertRaises(RuntimeError):
                dns_rcode('health.capstone.test', 1, port, require_answer=True,
                          expected_rdata=b'\xc0\x00\x02\x01')
            thread.join()

    def test_wrong_transaction_id_is_rejected(self):
        port,t=self.respond(lambda q: bytes([q[0]^1])+q[1:2]+b'\x81\x80'+q[4:])
        with self.assertRaises(RuntimeError): dns_rcode('health.capstone.test',1,port)
        t.join()
    def test_query_packet_and_truncated_packet_are_rejected(self):
        for mutate in (lambda q:q,lambda q:q[:5],lambda q:q[:2]+b'\x83\x80'+q[4:]):
            port,t=self.respond(mutate)
            with self.assertRaises(RuntimeError): dns_rcode('health.capstone.test',1,port)
            t.join()
    def test_wrong_question_is_rejected(self):
        port,t=self.respond(lambda q:q[:2]+b'\x81\x80'+q[4:-2]+b'\x00\x03')
        with self.assertRaises(RuntimeError): dns_rcode('health.capstone.test',1,port)
        t.join()

if __name__=='__main__':unittest.main()
