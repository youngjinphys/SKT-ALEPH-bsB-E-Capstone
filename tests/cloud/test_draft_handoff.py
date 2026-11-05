"""Read-only preparation for independently signing a target-specific draft."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys
import base64
import hashlib
import hmac
import json
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cloud.app import app
from cloud.state import MemoryStore, materialize
from cloud.operations import trust_key, publish
from aleph_policy_sync.snapshot import canonical, sign_policy, verify_envelope


class DraftHandoffTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.now = datetime.now(timezone.utc)
        self.key = Ed25519PrivateKey.generate()
        self.pem = self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        with materialize(self.store.load()['state']) as work:
            trust_key(work, {'role':'policy','public_key':self.pem,'confirm':'TRUST_PUBLIC_KEY'})
            rev = work.service.manual_blacklist()['revision']
            work.service.save_manual_block({'domain':'incident.example.net','reviewer':'Test operator',
                'reason':'Reviewed synthetic domain and subtree impact',
                'expires_at':(self.now+timedelta(hours=1)).isoformat(),
                'acknowledge_subtree':True,'expected_revision':rev,'confirm':'UPSERT_MANUAL_SUBTREE'})
            manual = work.service.manual_blacklist()
            result = work.service.build({'fingerprint':None,'review_set_revision':'NOT_PRESENT',
                'manual_revision':manual['revision'],'confirm_replacement':True,'acknowledge_user_notice':True})
            self.name = result['draft']
            self.raw = work.service.download(self.name)
            self.store.save(0,work.export())
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.path = '/api/ops/drafts/'+self.name+'/handoff/'
        self.env = patch.dict(os.environ, {'CAPSTONE_SITE_ORIGIN':'https://skt-aleph-capstone.vercel.app'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.storage = patch('cloud.app.get_store',return_value=self.store)
        self.storage.start(); self.addCleanup(self.storage.stop)
        self.identity = patch('cloud.app.require_operator',return_value='operator@example.org')
        self.identity.start(); self.addCleanup(self.identity.stop)

    def handoff(self, device='edge-69'):
        return self.client.get(self.path+device)

    def test_draft_handoff_is_read_only_and_target_bound(self):
        revision=self.store.load()['revision']
        response=self.handoff(); self.assertEqual(response.status_code,200,response.text)
        value=response.json()
        self.assertEqual(value['draft']['name'],self.name)
        self.assertEqual(value['draft']['rules'],1)
        self.assertEqual(value['draft']['download_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(value['target']['device_id'],'edge-69')
        self.assertEqual(value['target']['current_sequence'],0)
        self.assertEqual(value['target']['next_sequence'],1)
        self.assertIsNone(value['target']['node_sequence'])
        self.assertFalse(value['target']['watermark_warning'])
        self.assertIsNone(value['target']['node_state'])
        self.assertFalse(value['target']['registered'])
        self.assertEqual(value['feed']['url'],'https://skt-aleph-capstone.vercel.app/v1/policies/edge-69/current.json')
        self.assertEqual(len(value['signing']['key_ids']),1)
        self.assertTrue(value['signing']['can_sign'])
        self.assertIsNone(value['signing']['envelope_sha256'])
        self.assertIn('edge-69',value['signing']['argv_template'])
        self.assertIn('apps/policy-sync/src',value['signing']['pythonpath_components'])
        self.assertEqual(self.store.load()['revision'],revision)

    def test_existing_signed_feed_controls_sequence_and_is_independently_verified(self):
        with materialize(self.store.load()['state']) as work:
            envelope=sign_policy(self.raw,self.key,target='edge-69',sequence=7)
            publish(work,{'device_id':'edge-69','envelope':envelope,'expected_sequence':0,
                          'ack_withdrawals':False,'ack_key_rotation':False})
            self.store.save(self.store.load()['revision'],work.export())
        response=self.handoff(); self.assertEqual(response.status_code,200,response.text)
        value=response.json()
        self.assertEqual(value['target']['current_sequence'],7)
        self.assertEqual(value['target']['next_sequence'],8)
        self.assertEqual(value['signing']['reason'],'NOT_NEWER_THAN_PUBLICATION')
        self.assertEqual(value['draft']['policy_sha256'],envelope['payload']['policy_sha256'])
        feed=self.client.get('/v1/policies/edge-69/current.json')
        self.assertEqual(feed.status_code,200,feed.text)
        with materialize(self.store.load()['state']) as work:
            payload,parsed=verify_envelope(feed.content,expected_device='edge-69',trust_dir=work.root/'policy-trust')
        self.assertEqual(payload['sequence'],7)
        self.assertEqual(parsed.digest,value['draft']['policy_sha256'])

    def test_invalid_device_query_and_unverifiable_publication_rejected(self):
        for device in ('../edge','edge;id','', 'a'*65):
            self.assertNotEqual(self.handoff(device).status_code,200,device)
        self.assertNotEqual(self.client.get(self.path+'edge-69?device_id=edge-70').status_code,200)
        with materialize(self.store.load()['state']) as work:
            folder=work.root/'feed'/'edge-69';folder.mkdir()
            (folder/'current.json').write_bytes(b'{}');(folder/'current.json').chmod(0o600)
            self.store.save(self.store.load()['revision'],work.export())
        self.assertEqual(self.handoff().status_code,409)

    def test_expired_or_short_draft_is_not_recommended_for_signing(self):
        from cloud.handoff import make_handoff
        with materialize(self.store.load()['state']) as work:
            short=make_handoff(work,self.name,'edge-69',now=self.now+timedelta(minutes=59))
            expired=make_handoff(work,self.name,'edge-69',now=self.now+timedelta(hours=2))
        self.assertFalse(short['signing']['can_sign'])
        self.assertFalse(expired['signing']['can_sign'])
        self.assertNotEqual(short['signing']['reason'],expired['signing']['reason'])

    def test_unauthenticated_access_and_invalid_origin_are_rejected(self):
        self.identity.stop()
        self.assertEqual(self.handoff().status_code,401)
        self.identity.start()
        with patch.dict(os.environ,{'CAPSTONE_SITE_ORIGIN':'https://user@evil.example/path'}):
            self.assertEqual(self.handoff().status_code,503)

    def test_corrupt_signer_key_is_not_presented_as_trusted(self):
        snapshot=self.store.load()
        name=next(path for path in snapshot['state']['files'] if path.startswith('policy-trust/'))
        snapshot['state']['files'][name]='invalid public key'
        self.store.save(snapshot['revision'],snapshot['state'])
        self.assertEqual(self.handoff().status_code,503)

    def test_sequence_beyond_dashboard_precision_is_rejected(self):
        with materialize(self.store.load()['state']) as work:
            envelope=sign_policy(self.raw,self.key,target='edge-69',sequence=(1 << 53)-1)
            publish(work,{'device_id':'edge-69','envelope':envelope,'expected_sequence':0,
                          'ack_withdrawals':False,'ack_key_rotation':False})
            self.store.save(self.store.load()['revision'],work.export())
        response=self.handoff()
        self.assertEqual(response.status_code,409,response.text)

    def test_signed_node_report_ahead_blocks_signing_without_skipping_sequence(self):
        from aleph_policy_sync.telemetry import signed_report
        key=Ed25519PrivateKey.generate()
        pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        with materialize(self.store.load()['state']) as work:
            kid=trust_key(work,{'role':'node','public_key':pem,'confirm':'TRUST_PUBLIC_KEY'})['key_id']
            work.service.register_node({'device_id':'edge-69','dns_address':'192.168.7.69','label':'Test node','key_id':kid})
            report={'format':2,'type':'aleph-dns-node-report','device_id':'edge-69',
                    'report_sequence':1,'reported_at':self.now.isoformat(),
                    'dns_address':'192.168.7.69','policy_sequence':5,'policy_sha256':'a'*64,
                    'applied_at':self.now.isoformat(),'attestation':'ATTESTED',
                    'probe':{'domain':None,'udp':None,'tcp':None,'baseline':None}}
            work.service.receive_node_report(signed_report(report,key))
            self.store.save(self.store.load()['revision'],work.export())
        response=self.handoff()
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['target']['current_sequence'],0)
        self.assertEqual(result['target']['next_sequence'],1)
        self.assertEqual(result['target']['node_sequence'],'5')
        self.assertTrue(result['target']['watermark_warning'])
        self.assertFalse(result['signing']['can_sign'])
        self.assertEqual(result['signing']['reason'],'NODE_SEQUENCE_AHEAD')
        other=self.handoff('edge-70').json()
        self.assertIsNone(other['target']['node_sequence'])
        self.assertFalse(other['target']['watermark_warning'])

    def test_feed_origin_override_and_target_specific_node(self):
        from cloud.enrollment import enroll
        from aleph_policy_sync.enrollment import make_enrollment
        request=make_enrollment(Ed25519PrivateKey.generate(),'edge-70','192.168.7.70','Other node')
        with materialize(self.store.load()['state']) as work:
            enroll(work,{'enrollment':request,'expected_key_id':request['key_id'],'confirm':'ENROLL_NODE'})
            self.store.save(self.store.load()['revision'],work.export())
        with patch.dict(os.environ,{'ALEPH_POLICY_FEED_ORIGIN':'https://policy.example.org'}):
            chosen=self.handoff('edge-70').json()
            self.assertEqual(chosen['feed']['url'],'https://policy.example.org/v1/policies/edge-70/current.json')
            self.assertTrue(chosen['target']['registered'])
            self.assertEqual(chosen['target']['node_state']['device_id'],'edge-70')
            self.assertEqual(chosen['target']['node_state']['state'],'NO_REPORT')
            self.assertFalse(self.handoff('edge-69').json()['target']['registered'])
        for origin in ('http://example.org','https://evil.example/x','https://evil.example?x=1',
                       'https://user@evil.example','https://example.org:99999'):
            with self.subTest(origin=origin), patch.dict(os.environ,{'ALEPH_POLICY_FEED_ORIGIN':origin}):
                self.assertEqual(self.handoff().status_code,503)

    def test_signed_sites_get_uses_existing_assertion_verification(self):
        origin='https://test.chatgpt.site'; key=b'0123456789abcdef0123456789abcdef'
        b64=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
        path=self.path+'edge-69';now=int(time.time())
        claims={'v':1,'iss':origin,'aud':'aleph-ops','email':'owner@example.org',
                'iat':now,'exp':now+30,'jti':str(uuid.uuid4()),'method':'GET',
                'path':path,'body_sha256':hashlib.sha256(b'').hexdigest()}
        encoded=b64(json.dumps(claims,separators=(',',':')).encode())
        headers={'X-Aleph-Sites-Assertion':encoded,
                 'X-Aleph-Sites-Signature':b64(hmac.digest(key,encoded.encode(),'sha256'))}
        with patch.dict(os.environ,{'CAPSTONE_SITES_BRIDGE_ORIGIN':origin,
                                    'CAPSTONE_SITES_BRIDGE_SECRET':b64(key),
                                    'CAPSTONE_OPS_ALLOWED_EMAILS':'owner@example.org'}):
            result=self.client.get(path,headers=headers)
            self.assertEqual(result.status_code,200,result.text)
            headers['X-Aleph-Sites-Signature']='a'*43
            self.assertEqual(self.client.get(path,headers=headers).status_code,401)


if __name__=='__main__':unittest.main()
