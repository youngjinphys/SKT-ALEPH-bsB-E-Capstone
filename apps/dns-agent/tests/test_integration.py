"""Real dnsmasq + independent dig oracle, all on loopback; no public DNS required."""
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from dns_agent.policy import render_config, utcnow
from dns_agent.runtime import DnsmasqRuntime, dns_rcode
from dns_agent.transaction import Store, Agent

BINARY = shutil.which('dnsmasq')
DIG = shutil.which('dig')
AVAILABLE = BINARY is not None and DIG is not None and os.geteuid() != 0
if os.environ.get('REQUIRE_DNSMASQ') == '1' and not AVAILABLE:
    raise RuntimeError('real DNS tests required: install dnsmasq-base/dnsutils and use a non-root account')

def free_port():
    # Port is subsequently verified by the runtime; bind races cause test failure, not a false pass.
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]

def fixture(now):
    end=(now+timedelta(minutes=3)).isoformat()
    return {'issued_at':now.isoformat(),'expires_at':end,'rules':[
        {'domain':name,'decision':decision,'scope':'SUBTREE','approved':True,
         'expires_at':(now+timedelta(minutes=1)).isoformat(),'evidence':'controlled-fixture'}
        for name,decision in [('blocked.test','BLOCK'),('good.test','ALLOW'),('warn.test','WARN')]]}

@unittest.skipUnless(AVAILABLE,'real dnsmasq/dig unavailable or privileged account; NOT an integration pass')
class RealDnsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.port=free_port(); self.upstream_port=free_port()
        while self.upstream_port==self.port:self.upstream_port=free_port()
        self.now=utcnow().replace(microsecond=0);self.obj=fixture(self.now)
        config=(f'port={self.upstream_port}\nlisten-address=127.0.0.1\nbind-interfaces\n'
                'no-resolv\nno-hosts\ncache-size=0\nlocal=/test/\n'
                'host-record=blocked.test,192.0.2.20,2001:db8::20\n'
                'host-record=child.blocked.test,192.0.2.21,2001:db8::21\n'
                'host-record=other-blocked.test,192.0.2.22,2001:db8::22\n'
                'host-record=good.test,192.0.2.30,2001:db8::30\n'
                'host-record=warn.test,192.0.2.40,2001:db8::40\n'
                'host-record=naver.com,192.0.2.51,2001:db8::51\n'
                'host-record=daum.net,192.0.2.52,2001:db8::52\n'
                'host-record=google.com,192.0.2.53,2001:db8::53\n'
                'cname=alias.test,blocked.test\n')
        path=self.root/'upstream.conf';path.write_text(config)
        self.upstream=subprocess.Popen([BINARY,'--no-daemon','--pid-file','--log-facility=-',
                                        '--conf-file='+str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.addCleanup(self._stop_upstream)
        for _ in range(40):
            if self.upstream.poll() is not None:self.fail('fixture dnsmasq failed to start')
            try:
                if dns_rcode('good.test',1,self.upstream_port)==0:break
            except OSError:time.sleep(.05)
        else:self.fail('fixture not ready')
        self.store=Store(self.root/'state');self.store.__enter__()
        self.addCleanup(self.store.__exit__,None,None,None)
        self.runtime=DnsmasqRuntime(BINARY,self.port);self.addCleanup(self.runtime.stop)
        self.agent=Agent(self.store,self.runtime,port=self.port,upstream='127.0.0.1',upstream_port=self.upstream_port)
    def _stop_upstream(self):
        self.upstream.terminate()
        try:self.upstream.wait(2)
        except subprocess.TimeoutExpired:self.upstream.kill();self.upstream.wait()
        self.tmp.cleanup()
    def apply(self,obj=None,now=None):
        return self.agent.cycle(json.dumps(obj or self.obj).encode(),now=now or self.now)
    def dig(self,name,kind='A',tcp=False,upstream=False):
        cmd=[DIG,'@127.0.0.1','-p',str(self.upstream_port if upstream else self.port),
             name,kind,'+time=1','+tries=1','+noall','+comments','+answer']
        if tcp:cmd.append('+tcp')
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=4)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        return p.stdout
    def test_periodic_health_detects_normal_aaaa_canary_failure_on_both_transports(self):
        self.apply()
        for failing_tcp in (False, True):
            with self.subTest(tcp=failing_tcp):
                def query(name, qtype, port, **kwargs):
                    if name == 'blocked.test' and qtype == 28 and kwargs.get('tcp') == failing_tcp:
                        return 0
                    return dns_rcode(name, qtype, port, **kwargs)
                self.runtime._last_probe_at = 0
                with patch('dns_agent.runtime.dns_rcode', side_effect=query):
                    self.assertFalse(self.runtime.healthy())

    def test_generated_site_test_policy_blocks_real_names_in_isolated_resolver(self):
        # Fixture addresses are documentation-only; no public site is contacted.
        script = Path(__file__).resolve().parents[3] / 'scripts/build_site_test_policy.py'
        output = subprocess.check_output([sys.executable, str(script)], timeout=5)
        domains = ('naver.com', 'daum.net', 'google.com')
        for name in domains:
            self.assertIn('status: NOERROR', self.dig(name, 'A', upstream=True))
            self.assertIn('192.0.2.', self.dig(name, 'A', upstream=True))
            self.assertIn('2001:db8::', self.dig(name, 'AAAA', upstream=True))
        self.agent.cycle(output)
        for name in domains:
            for kind in ('A', 'AAAA'):
                for tcp in (False, True):
                    with self.subTest(name=name, kind=kind, tcp=tcp):
                        self.assertIn('status: NXDOMAIN', self.dig(name, kind, tcp=tcp))
        self.agent.cycle(None, now=utcnow() + timedelta(minutes=16))
        for name in domains:
            for kind in ('A', 'AAAA'):
                for tcp in (False, True):
                    with self.subTest(expired=name, kind=kind, tcp=tcp):
                        self.assertIn('status: NOERROR', self.dig(name, kind, tcp=tcp))

    def test_normal_start_rejects_non_nxdomain_a_canary(self):
        # Keep the real resolver and packets, but simulate a wrong A result
        # while the health records and AAAA answer continue to work normally.
        config = render_config(('blocked.test',), port=self.port, upstream='127.0.0.1',
                               upstream_port=self.upstream_port)
        path = self.root/'normal.conf'
        path.write_text(config)
        def query(name, qtype, port, **kwargs):
            if name == 'blocked.test' and qtype == 1:
                return 0
            return dns_rcode(name, qtype, port, **kwargs)
        with patch('dns_agent.runtime.dns_rcode', side_effect=query):
            with self.assertRaisesRegex(RuntimeError, 'health checks timed out'):
                self.runtime.start(path)
        self.assertFalse(self.runtime.alive())

    def _assert_start_checks_canary_for_both_types_and_transports(self, query):
        probes = {(c.args[1], c.kwargs['tcp']) for c in query.call_args_list
                  if c.args[0] == 'blocked.test'}
        self.assertEqual(probes, {(1, False), (28, False), (1, True), (28, True)})

    def test_http_start_rejects_wrong_sink_a_or_positive_aaaa(self):
        # Real dnsmasq serves a healthy health record but an invalid notice
        # response. Startup must reject it before reporting the service ready.
        self.runtime.stop()
        self.runtime = DnsmasqRuntime(BINARY, self.port, http_sink_ip='127.0.0.1')
        self.addCleanup(self.runtime.stop)
        good = render_config(('blocked.test',), port=self.port, upstream='127.0.0.1',
                             upstream_port=self.upstream_port, http_sink_ip='127.0.0.1')
        for bad in (good.replace('address=/blocked.test/127.0.0.1',
                                 'address=/blocked.test/127.0.0.2'),
                    good + 'address=/blocked.test/::1\n'):
            with self.subTest(config=bad):
                path = self.root/'invalid-notice.conf'
                path.write_text(bad)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'health checks timed out'):
                        self.runtime.start(path)
                    self.assertFalse(self.runtime.alive())
                finally:
                    self.runtime.stop()

    def test_opt_in_dns_http_notice_maps_a_and_suppresses_other_types(self):
        # Unlike the default NXDOMAIN mode, explicitly approved BLOCK/WARN
        # intercept A queries for the HTTP notice sink. This is a lab only.
        self.runtime.stop()
        self.runtime=DnsmasqRuntime(BINARY,self.port,http_sink_ip='127.0.0.1')
        self.addCleanup(self.runtime.stop)
        self.agent=Agent(self.store,self.runtime,port=self.port,
                         upstream='127.0.0.1',upstream_port=self.upstream_port,
                         http_sink_ip='127.0.0.1')
        with patch('dns_agent.runtime.dns_rcode', wraps=dns_rcode) as query:
            self.apply()
        self._assert_start_checks_canary_for_both_types_and_transports(query)
        self.runtime._last_probe_at = 0
        with patch('dns_agent.runtime.dns_rcode', wraps=dns_rcode) as periodic_query:
            self.assertTrue(self.runtime.healthy())
        self._assert_start_checks_canary_for_both_types_and_transports(periodic_query)
        for tcp in (False,True):
            for domain in ('blocked.test','child.blocked.test','warn.test'):
                output=self.dig(domain,'A',tcp=tcp)
                self.assertIn('status: NOERROR',output)
                self.assertIn('127.0.0.1',output)
                for kind in ('AAAA','HTTPS'):
                    other=self.dig(domain,kind,tcp=tcp)
                    self.assertIn('status: NOERROR',other)
                    self.assertNotIn('2001:db8',other)
            good=self.dig('good.test','A',tcp=tcp)
            self.assertIn('192.0.2.30',good)
        self.assertTrue(self.runtime.healthy())

    def test_block_subtree_allow_warn_and_transport(self):
        self.assertIn('192.0.2.20',self.dig('blocked.test',upstream=True))
        with patch('dns_agent.runtime.dns_rcode', wraps=dns_rcode) as query:
            self.apply()
        self._assert_start_checks_canary_for_both_types_and_transports(query)
        self.runtime._last_probe_at = 0
        with patch('dns_agent.runtime.dns_rcode', wraps=dns_rcode) as periodic_query:
            self.assertTrue(self.runtime.healthy())
        self._assert_start_checks_canary_for_both_types_and_transports(periodic_query)
        for tcp in (False,True):
            for kind in ('A','AAAA','HTTPS'):
                for name in ('blocked.test','child.blocked.test'):
                    self.assertIn('status: NXDOMAIN',self.dig(name,kind,tcp))
            for name,expected in [('good.test','192.0.2.30'),('warn.test','192.0.2.40'),('other-blocked.test','192.0.2.22')]:
                out=self.dig(name,tcp=tcp)
                self.assertIn('status: NOERROR',out);self.assertIn(expected,out)
        self.assertIn('2001:db8::30',self.dig('good.test','AAAA'))
    def test_withdraw_and_invalid_update(self):
        self.apply();self.agent.cycle(b'{broken',now=self.now)
        self.assertIn('status: NXDOMAIN',self.dig('blocked.test'))
        self.obj['issued_at']=(self.now+timedelta(seconds=1)).isoformat();self.obj['rules']=[]
        self.apply(now=self.now+timedelta(seconds=1))
        self.assertIn('192.0.2.20',self.dig('blocked.test'))
    def test_expiry_does_not_need_fresh_file(self):
        self.apply();self.agent.cycle(None,now=self.now+timedelta(seconds=61))
        self.assertIn('192.0.2.20',self.dig('blocked.test'))
    def test_upstream_down_is_not_confused_with_block(self):
        self.apply();self.upstream.terminate();self.upstream.wait(2)
        self.assertIn('status: NXDOMAIN',self.dig('blocked.test'))
        # Positive upstream resolution is not asserted when its server is absent.
        self.assertTrue(self.runtime.alive())
    def test_alias_is_outside_qname_block_guarantee(self):
        self.apply();out=self.dig('alias.test')
        # dnsmasq may return the permitted alias plus the blocked target's address.
        # Record the observation; no claim that QNAME policy filters the answer chain.
        # This deliberately demonstrates the current QNAME-only protection gap.
        # Do not turn this into a claim of complete chain-of-alias coverage.
        self.assertIn('status: NOERROR', out)
        self.assertIn('CNAME', out)
        self.assertIn('blocked.test.', out)
        self.assertIn('192.0.2.20', out)
        print('CNAME bypass observation: '+out.replace('\n',' '),flush=True)
    def _restart_command(self, policy):
        return [sys.executable, '-m', 'dns_agent', 'run', str(policy),
                '--state-dir', str(self.root/'state'), '--port', str(self.port),
                '--upstream', '127.0.0.1', '--upstream-port', str(self.upstream_port)]
    def _release_agent(self):
        self.runtime.stop()
        self.store.__exit__(None, None, None)
    def _check_restarted_dns(self, policy, expected_rcode):
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        proc=subprocess.Popen(self._restart_command(policy), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    self.fail('agent exited before recovery: '+proc.stderr.read())
                try:
                    if dns_rcode('blocked.test', 1, self.port, timeout=.1)==expected_rcode:
                        if expected_rcode == 0:
                            self.assertIn('192.0.2.20', self.dig('blocked.test'))
                        return
                except OSError:
                    pass
                time.sleep(.05)
            self.fail('restarted listener did not return the expected response')
        finally:
            if proc.poll() is None: proc.terminate()
            proc.communicate(timeout=5)
    def test_restart_recovers_saved_policy_when_source_missing_or_invalid(self):
        self.apply(); self._release_agent()
        policy=self.root/'policy.json'
        for content in (None, '{broken'):
            with self.subTest(source=content):
                if content is None: policy.unlink(missing_ok=True)
                else: policy.write_text(content)
                self._check_restarted_dns(policy, 3)
    def test_recovered_listener_accepts_new_policy_and_withdraws_block(self):
        self.apply(); self._release_agent()
        policy=self.root/'policy.json'
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        proc=subprocess.Popen(self._restart_command(policy),env=env,
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        try:
            def await_rcode(expected):
                for _ in range(100):
                    if proc.poll() is not None:
                        self.fail('agent exited during update: '+proc.stderr.read())
                    try:
                        if dns_rcode('blocked.test',1,self.port,timeout=.1)==expected:
                            return
                    except OSError:
                        pass
                    time.sleep(.05)
                self.fail('DNS response did not reach expected state')
            await_rcode(3)
            withdrawal=fixture(self.now+timedelta(seconds=1)); withdrawal['rules']=[]
            policy.write_text(json.dumps(withdrawal))
            await_rcode(0)
            self.assertIn('192.0.2.20',self.dig('blocked.test'))
        finally:
            if proc.poll() is None: proc.terminate()
            proc.communicate(timeout=5)
    def test_restart_does_not_restore_expired_saved_block(self):
        past=self.now-timedelta(minutes=4)
        self.apply(fixture(past), now=past); self._release_agent()
        self._check_restarted_dns(self.root/'missing.json', 0)
    def test_missing_or_invalid_policy_without_saved_state_does_not_start(self):
        self._release_agent()
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        policy=self.root/'policy.json'
        for content in (None, '{broken'):
            with self.subTest(source=content):
                if content is not None: policy.write_text(content)
                proc=subprocess.run(self._restart_command(policy), env=env,
                                    capture_output=True,text=True,timeout=5)
                self.assertNotEqual(proc.returncode, 0)
                with self.assertRaises(OSError): dns_rcode('blocked.test',1,self.port,timeout=.2)
    def test_missing_policy_still_recovers_interrupted_transaction(self):
        self.apply(); self._release_agent()
        state_dir=self.root/'state'
        saved=json.loads((state_dir/'state.json').read_text())
        (state_dir/'pending.json').write_text(json.dumps({'previous':saved}))
        (state_dir/'active.conf').write_text('incomplete candidate')
        self._check_restarted_dns(self.root/'missing.json', 3)
        self.assertEqual((state_dir/'active.conf').read_text(),saved['config'])
        self.assertFalse((state_dir/'pending.json').exists())
    def test_missing_policy_does_not_bypass_corrupt_journal(self):
        self.apply(); self._release_agent()
        active=self.root/'state'/'active.conf'; before=active.read_bytes()
        journal=self.root/'state'/'pending.json'; journal.write_text('{broken')
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        proc=subprocess.run(self._restart_command(self.root/'missing.json'), env=env,
                            capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,3,proc.stderr)
        self.assertEqual(active.read_bytes(),before)
        self.assertEqual(journal.read_text(),'{broken')
    def test_supervisor_death_closes_listener(self):
        # Separate supervisor with its own state, not this test's runtime.
        policy=self.root/'policy.json';policy.write_text(json.dumps(self.obj))
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        proc=subprocess.Popen([sys.executable,'-m','dns_agent','run',str(policy),
                               '--state-dir',str(self.root/'child-state'),'--port',str(self.port),
                               '--upstream','127.0.0.1','--upstream-port',str(self.upstream_port)],
                              env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                if proc.poll() is not None:self.fail('agent exited early')
                try:
                    if dns_rcode('blocked.test',1,self.port)==3:break
                except OSError:time.sleep(.05)
            else:self.fail('agent not ready')
            proc.kill();proc.wait(3)
            time.sleep(.3)
            with self.assertRaises(OSError):dns_rcode('blocked.test',1,self.port,timeout=.2)
        finally:
            if proc.poll() is None:proc.kill();proc.wait(3)

if __name__=='__main__':unittest.main()
