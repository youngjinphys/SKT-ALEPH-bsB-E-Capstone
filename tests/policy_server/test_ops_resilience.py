"""Regressions for real operator failure paths; no external network or credentials."""
import json, os, socket, struct, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from policy_server import intel
from policy_server.refresh_bridge import RefreshServer, BridgeError, serve

class CollectorResilience(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
    def test_persisted_status_validates_values_not_dictionary_key_names(self):
        bad={'state':'ERROR','requested_at':None,'completed_at':None,'error_code':{'private':'unexpected value'}}
        intel.write_json(self.root/'gui-refresh-state.json',bad)
        with self.assertRaisesRegex(BridgeError,'status'):
            RefreshServer(self.root,self.root/'key',12345)
    def test_disconnected_client_does_not_stop_next_valid_status_request(self):
        server=RefreshServer(self.root,self.root/'key',12345)
        class Peer:
            def __init__(self,broken=False):self.parts=[b'{"action":"status"}',b''];self.broken=broken;self.reply=None
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def settimeout(self,*args):pass
            def getsockopt(self,*args):return struct.pack('3i',77,12345,12345)
            def recv(self,*args):return self.parts.pop(0)
            def sendall(self,raw):
                if self.broken:raise BrokenPipeError('client disappeared')
                self.reply=json.loads(raw)
        first,second=Peer(True),Peer()
        class Listener:
            family=socket.AF_UNIX;type=socket.SOCK_STREAM
            def __init__(self):self.peers=[first,second]
            def accept(self):
                if not self.peers:raise KeyboardInterrupt()
                return self.peers.pop(0),None
        try:serve(server,Listener())
        except KeyboardInterrupt:pass
        except BrokenPipeError:pass
        self.assertIsNotNone(second.reply,'one disconnected client killed the collector loop')
        self.assertEqual(second.reply['state'],'IDLE')

class ReviewBuildIntent(unittest.TestCase):
    def test_stale_review_set_cannot_be_used_to_build_policy(self):
        from datetime import datetime,timezone
        from policy_server.console import ConsoleService,ConsoleConflict
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);root.chmod(0o700)
            token=root/'token';token.write_text('t'*48);token.chmod(0o600)
            service=ConsoleService(root,token)
            url='https://malicious-fixture.example.org/login';now=datetime.now(timezone.utc)
            collected=intel.collect_urls((url+'\n').encode(),source='openphish',fetched_at=now)
            verified=intel.verify_collected(collected,'test-key',checked_at=now,fetch=lambda *a,**k:json.dumps({'threats':[{'url':url,'threatTypes':['SOCIAL_ENGINEERING']}],'cacheDuration':'300s'}).encode())
            intel.write_json(root/'verified.json',verified)
            before=service.reviews();item=before['items'][0]
            service.update_review(dict(id=item['id'],revision=item['revision'],fingerprint=before['fingerprint'],reviewer='Operator',reason='Synthetic threat review including subtree impact',approved=True,acknowledge_subtree=True))
            request=dict(fingerprint=before['fingerprint'],review_set_revision=before['review_set_revision'],confirm_replacement=True,acknowledge_user_notice=True)
            with self.assertRaises(ConsoleConflict):service.build(request)
            current=service.reviews();request['review_set_revision']=current['review_set_revision']
            self.assertEqual(service.build(request)['rules'],1)
