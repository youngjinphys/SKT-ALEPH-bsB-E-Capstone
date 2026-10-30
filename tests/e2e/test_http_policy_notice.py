"""A real, local HTTP redirect follows an applied, checksum-verified DNS policy.

No live phishing domains, DNS settings, routing or HTTP proxying are involved.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/dns-agent/src'))
from dns_agent import http_notice as notice
from dns_agent.policy import parse_policy, render_config

NOW=datetime.now(timezone.utc).replace(microsecond=0)


def policy_text():
    return {
        'issued_at':(NOW-timedelta(minutes=1)).isoformat(),
        'expires_at':(NOW+timedelta(minutes=30)).isoformat(),
        'rules':[
            {'domain':dom,'decision':decision,'scope':'SUBTREE','approved':approved,
             'expires_at':(NOW+timedelta(minutes=20)).isoformat(),'evidence':'approved-test-case'}
            for dom,decision,approved in (
                ('blocked.test','BLOCK',True),('warn.test','WARN',True),
                ('allowed.test','ALLOW',True),('unapproved.test','BLOCK',False))]
    }


def request(port,host,method='GET',path='/foo?secret=very-secret'):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
    try:
        conn.request(method,path,headers={'Host':host,'Referer':'http://other.test/?token=secret'})
        response=conn.getresponse()
        return response.status,dict(response.getheaders()),response.read()
    finally:conn.close()


@contextmanager
def running(handler,client_net=ipaddress.IPv4Network('127.0.0.1/32')):
    with notice.NoticeHTTPServer(('127.0.0.1',0),handler) as srv:
        srv.client_net=client_net
        thread=threading.Thread(target=srv.serve_forever,daemon=True)
        thread.start()
        try:yield srv.server_port
        finally:
            srv.shutdown();thread.join(2)


class HTTPNoticeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.state=self.root/'state';self.state.mkdir()
        self.assets=self.root/'public';self.assets.mkdir()
        for route,(name,_) in notice.ASSETS.items():
            if route!='/': (self.assets/name).write_text(name,encoding='utf-8')
        self.doc=policy_text()
        self.install_state()

    def install_state(self,http_notice=True):
        raw=json.dumps(self.doc).encode()
        policy=parse_policy(raw)
        now=datetime.now(timezone.utc)
        blocked=policy.blocked(now)
        warned=policy.warned(now)
        cfg=render_config(blocked,port=35353,upstream='127.0.0.1',
                          upstream_port=35453,listen_address='127.0.0.1',
                          warned=warned if http_notice else (),
                          http_sink_ip='127.0.0.1' if http_notice else None)
        state={'policy':policy.raw.decode(),'policy_sha256':policy.digest,
               'config':cfg,'config_sha256':hashlib.sha256(cfg.encode()).hexdigest(),
               'applied_at':now.isoformat(),'blocked_count':len(blocked)}
        (self.state/'state.json').write_text(json.dumps(state))
        (self.state/'active.conf').write_text(cfg)
        return state

    def conf(self,http_port=38080,portal_port=35173):
        return notice.validate_settings(listen='127.0.0.1',client_cidr='127.0.0.1/32',
                                        redirect_port=http_port,portal_port=portal_port,
                                        state_dir=self.state,static_root=self.assets)

    def test_active_dns_state_routes_block_and_warn_only(self):
        routes=notice.read_active_routes(self.state,'127.0.0.1')
        self.assertEqual(notice.classify('blocked.test',routes),'BLOCK')
        self.assertEqual(notice.classify('x.blocked.test',routes),'BLOCK')
        self.assertEqual(notice.classify('warn.test',routes),'WARN')
        self.assertIsNone(notice.classify('allowed.test',routes))
        self.assertIsNone(notice.classify('unapproved.test',routes))
        self.assertIsNone(notice.classify('fakeblocked.test',routes))

    def test_redirects_are_fixed_and_follow_the_existing_pages(self):
        conf=self.conf()
        with running(notice.redirect_handler(conf)) as redirect:
            for host,path,expect in [
                ('blocked.test','/private?password=hidden','phishing-block.html'),
                ('sub.blocked.test','/xx?secret=data','phishing-block.html'),
                ('warn.test','/account?token=secret','phishing-warning-continue.html'),
            ]:
                with self.subTest(host=host):
                    code,h,body=request(redirect,host,path=path)
                    self.assertEqual(code,302)
                    self.assertEqual(h['Location'],f'http://127.0.0.1:35173/{expect}')
                    self.assertEqual(h['Cache-Control'],'no-store')
                    self.assertEqual(h['Referrer-Policy'],'no-referrer')
                    self.assertNotIn('hidden',str(h))
                    self.assertNotIn('secret',str(h))
                    self.assertEqual(body,b'')
            for host in ('allowed.test','unapproved.test','notlisted.test'):
                self.assertEqual(request(redirect,host)[0],404)
            self.assertEqual(request(redirect,'blocked.test',method='POST')[0],405)
            self.assertNotIn('Location',request(redirect,'blocked.test',method='POST')[1])

    def test_head_portal_and_hidden_files(self):
        conf=self.conf()
        with running(notice.portal_handler(conf,notice.load_public_assets(self.assets))) as port:
            code,h,b=request(port,'127.0.0.1:35173',method='HEAD',path='/phishing-block.html')
            self.assertEqual(code,200);self.assertEqual(b,b'')
            self.assertEqual(h['Content-Length'],str(len('phishing-block.html')))
            self.assertIn("default-src 'none'",h['Content-Security-Policy'])
            self.assertEqual(request(port,'127.0.0.1:35173',path='/../README.md')[0],404)
            self.assertEqual(request(port,'127.0.0.1:35173',path='/.git/config')[0],404)
            self.assertEqual(request(port,'not-permitted.test:35173')[0],421)
            self.assertEqual(request(port,'127.0.0.1:35173',method='POST')[0],405)

    def test_open_proxy_host_injection_and_wrong_port_rejected(self):
        conf=self.conf()
        with running(notice.redirect_handler(conf)) as port:
            for host in ('https://blocked.test','blocked.test:443','blocked.test@evil.test',
                         '192.168.7.69','blocked.test:38081','blocked.test\r\n'):
                with self.subTest(host=repr(host)):
                    if '\r' in host: continue # http.client rejects CRLF before sending
                    self.assertEqual(request(port,host)[0],400)
            code,h,_=request(port,'blocked.test',path='http://evil.test/private')
            self.assertEqual(code,400)
            self.assertNotIn('Location',h)

    def test_corrupt_state_missing_http_mode_and_expired_rules_fail_safe(self):
        conf=self.conf()
        with running(notice.redirect_handler(conf)) as port:
            self.assertEqual(request(port,'blocked.test')[0],302)
            (self.state/'state.json').write_text('{broken')
            self.assertEqual(request(port,'blocked.test')[0],503)
            self.install_state(http_notice=False)
            self.assertEqual(request(port,'blocked.test')[0],503)
            self.install_state(http_notice=True)
            # State still contains a stale sink route, so refuse to trust it.
            with self.assertRaises(notice.NoticeError):
                notice.read_active_routes(self.state,'127.0.0.1',now=NOW+timedelta(minutes=21))

    def test_symlink_assets_are_rejected(self):
        (self.assets/'portal.js').unlink()
        (self.assets/'portal.js').symlink_to(self.root/'state'/'state.json')
        with self.assertRaises(notice.NoticeError):
            notice.load_public_assets(self.assets)

    def test_bind_client_cidr_and_manual_acknowledgement(self):
        with self.assertRaisesRegex(notice.NoticeError,'/24 or narrower'):
            notice.validate_settings(listen='192.168.7.69',client_cidr='192.168.0.0/16',
                                     redirect_port=80,portal_port=8080,
                                     state_dir=self.state,static_root=self.assets)
        with self.assertRaises(notice.NoticeError):
            notice.validate_settings(listen='0.0.0.0',client_cidr='192.168.7.0/24',
                                     redirect_port=80,portal_port=8080,
                                     state_dir=self.state,static_root=self.assets)
        with self.assertRaises(SystemExit):
            notice.main(['--listen-ip','127.0.0.1','--client-cidr','127.0.0.1/32',
                         '--state-dir',str(self.state),'--static-dir',str(self.assets)])

if __name__=='__main__': unittest.main()
