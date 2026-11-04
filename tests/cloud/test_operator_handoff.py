"""Preview/commit parity of the shared operations console."""
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import json,unittest
from fastapi.testclient import TestClient
from cloud.app import app
from cloud.state import MemoryStore,materialize,empty_state
from cloud.operations import import_evidence,trust_key,publish
from policy_server import intel
from policy_server.console import ConsoleConflict
from aleph_policy_sync.snapshot import sign_policy,canonical
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def evidence(at=None):
    at=at or datetime.now(timezone.utc)
    url='https://synthetic-malicious.example.org/login'
    col=intel.collect_urls((url+'\n').encode(),source='openphish',fetched_at=at)
    return intel.verify_collected(col,'test-only',checked_at=at,fetch=lambda *a,**k:json.dumps({'threats':[{'url':url,'threatTypes':['SOCIAL_ENGINEERING']}],'cacheDuration':'300s'}).encode())

class OperatorHandoff(unittest.TestCase):
    def setUp(self):
        self.store=MemoryStore();self.client=TestClient(app)
        self.headers={'Origin':'https://skt-aleph-capstone.vercel.app'}
        for target,value in [('cloud.app.get_store',self.store),('cloud.app.require_operator','operator@example.org')]:
            p=patch(target,return_value=value);p.start();self.addCleanup(p.stop)
    def post(self,path,body):return self.client.post('/api/ops/'+path,json=body,headers=self.headers)
    def test_node_removal_conflict_preserves_durable_state_and_audit(self):
        snapshot=self.store.load()
        with materialize(snapshot['state']) as w:
            key=Ed25519PrivateKey.generate()
            pem=key.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            key_id=trust_key(w,dict(role='node',public_key=pem,confirm='TRUST_PUBLIC_KEY'))['key_id']
            w.service.register_node(dict(device_id='edge-69',label='Test node',
                                         dns_address='192.168.7.69',key_id=key_id))
            self.store.save(snapshot['revision'],w.export())
        before=self.store.load()
        command=dict(device_id='edge-69',confirm='UNREGISTER_NODE')
        self.assertEqual(self.post('nodes/unregister',command).status_code,422)
        self.assertEqual(self.post('nodes/unregister',{**command,'expected_key_id':'f'*64}).status_code,409)
        self.assertEqual(self.store.load(),before)
        self.assertEqual(self.post('nodes/unregister',{**command,'expected_key_id':key_id}).status_code,200)
        self.assertEqual(self.store.load()['revision'],before['revision']+1)
        self.assertEqual(self.client.get('/api/ops/nodes').json(),[])

    def test_shared_node_unregister_route_is_supported(self):
        response=self.post('nodes/unregister',{'device_id':'edge-missing','confirm':'UNREGISTER_NODE'})
        self.assertNotEqual(response.status_code,404,'shared UI uses nodes/unregister, not nodes/remove')
    def test_device_publication_read_uses_selected_identity_without_mutating_state(self):
        snapshot=self.store.load()
        with materialize(snapshot['state']) as w:
            signing=Ed25519PrivateKey.generate()
            pem=signing.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            trust_key(w,dict(role='policy',public_key=pem,confirm='TRUST_PUBLIC_KEY'))
            now=datetime.now(timezone.utc);end=(now+timedelta(minutes=5)).isoformat()
            for dev,seq,host in [('edge-69',3,'first.example.org'),('edge-70',8,'second.example.org')]:
                policy={'issued_at':now.isoformat(),'expires_at':end,'rules':[
                    dict(domain=host,decision='BLOCK',scope='SUBTREE',approved=True,
                         expires_at=end,evidence='offline-fixture')]}
                envelope=sign_policy(canonical(policy),signing,target=dev,sequence=seq)
                publish(w,dict(device_id=dev,envelope=envelope,expected_sequence=0,
                               ack_withdrawals=False,ack_key_rotation=False))
            self.store.save(snapshot['revision'],w.export())
        before=self.store.load()
        second=self.client.get('/api/ops/deployment/edge-70')
        self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['device'],'edge-70')
        self.assertEqual(second.json()['sequence'],8)
        self.assertEqual(second.json()['rules'][0]['domain'],'second.example.org')
        self.assertEqual(self.client.get('/api/ops/deployment').json()['device'],'edge-69')
        missing=self.client.get('/api/ops/deployment/edge-unknown')
        self.assertEqual(missing.json()['state'],'NO_PUBLISHED_FILE')
        self.assertEqual(missing.json()['device'],'edge-unknown')
        self.assertEqual(self.store.load(),before)
        for bad in ('edge-70/extra','%2e%2e%2fsecret'):
            self.assertNotEqual(self.client.get('/api/ops/deployment/'+bad).status_code,200)

    def test_capability_response_does_not_promise_a_local_collector_on_vercel(self):
        r=self.client.get('/api/ops/capabilities')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['mode'],'cloud')
        self.assertFalse(r.json()['direct_refresh'])
        self.assertTrue(r.json()['evidence_upload'])
    def test_preview_requires_current_evidence_context_and_resets_new_approvals(self):
        first=evidence();preview=self.post('cloud/evidence/preview',{'verified':first})
        self.assertEqual(preview.status_code,200,preview.text)
        body={'verified':first,'confirm':'IMPORT_VERIFIED','context_revision':preview.json()['context_revision'],'fingerprint':preview.json()['fingerprint']}
        self.assertEqual(self.post('cloud/evidence',body).status_code,200)
        reviews=self.client.get('/api/ops/reviews').json();item=reviews['items'][0]
        new=evidence(datetime.now(timezone.utc)+timedelta(seconds=1))
        pre=self.post('cloud/evidence/preview',{'verified':new}).json()
        saved=self.post('reviews/save',dict(id=item['id'],revision=item['revision'],fingerprint=reviews['fingerprint'],approved=True,acknowledge_subtree=True,reviewer='Operator',reason='Review of synthetic URL and subtree blocking impact'))
        self.assertEqual(saved.status_code,200,saved.text)
        stale={'verified':new,'confirm':'IMPORT_VERIFIED','context_revision':pre['context_revision'],'fingerprint':pre['fingerprint']}
        self.assertEqual(self.post('cloud/evidence',stale).status_code,409)
        current=self.post('cloud/evidence/preview',{'verified':new}).json()
        stale['context_revision']=current['context_revision']
        self.assertEqual(self.post('cloud/evidence',stale).status_code,200)
        self.assertFalse(self.client.get('/api/ops/reviews').json()['items'][0]['approved'])
        self.assertTrue(any('evidence-archive/' in name for name in self.store.load()['state']['files']))
    def test_expired_cache_evidence_cannot_be_imported_as_current(self):
        old=evidence(datetime.now(timezone.utc)-timedelta(minutes=6))
        preview=self.post('cloud/evidence/preview',{'verified':old})
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertFalse(preview.json()['importable'])
        body={'verified':old,'confirm':'IMPORT_VERIFIED','context_revision':preview.json()['context_revision'],'fingerprint':preview.json()['fingerprint']}
        self.assertEqual(self.post('cloud/evidence',body).status_code,422)
        self.assertEqual(self.store.load()['revision'],0)
    def test_preview_operations_do_not_commit_state(self):
        key=Ed25519PrivateKey.generate()
        pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        pre=self.post('cloud/trust/preview',{'role':'policy','public_key':pem})
        self.assertEqual(pre.status_code,200,pre.text)
        self.assertEqual(self.store.load()['revision'],0)
        body={'role':'policy','public_key':pem,'confirm':'TRUST_PUBLIC_KEY','expected_key_id':pre.json()['key_id']}
        self.assertEqual(self.post('cloud/trust',{**body,'expected_key_id':'f'*64}).status_code,422)
        self.assertEqual(self.post('cloud/trust',body).status_code,200)
        now=datetime.now(timezone.utc)
        policy={'issued_at':now.isoformat(),'expires_at':(now+timedelta(minutes=5)).isoformat(),'rules':[]}
        envelope=sign_policy(canonical(policy),key,target='edge-69',sequence=1,confirm_empty=True)
        args={'device_id':'edge-69','envelope':envelope,'expected_sequence':0,'ack_withdrawals':False,'ack_key_rotation':False}
        before=self.store.load()['revision']
        result=self.post('cloud/publish/preview',args)
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(result.json()['published'])
        self.assertEqual(self.store.load()['revision'],before)
        self.assertEqual(self.client.get('/v1/policies/edge-69/current.json').status_code,404)

    def test_json_boundary_uses_declared_cloud_request_limit(self):
        # A syntactically valid cloud-sized payload reaches domain validation;
        # it must not be rejected by the smaller 900KB intel JSON decoder.
        result=self.post('cloud/trust/preview',{'role':'policy','public_key':'x'*950000})
        self.assertEqual(result.status_code,422,result.text)

    def test_higher_sequence_cannot_reintroduce_older_policy_issuance(self):
        now=datetime.now(timezone.utc);key=Ed25519PrivateKey.generate()
        pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        with materialize(empty_state()) as w:
            trust_key(w,dict(role='policy',public_key=pem,confirm='TRUST_PUBLIC_KEY'))
            def envelope(issued,seq):
                p={'issued_at':issued.isoformat(),'expires_at':(now+timedelta(minutes=5)).isoformat(),'rules':[]}
                return sign_policy(canonical(p),key,target='edge-69',sequence=seq,confirm_empty=True)
            args=dict(device_id='edge-69',envelope=envelope(now,1),expected_sequence=0,ack_withdrawals=True,ack_key_rotation=False)
            publish(w,args)
            with self.assertRaisesRegex(ValueError,'issuance'):
                publish(w,{**args,'envelope':envelope(now-timedelta(seconds=5),2),'expected_sequence':1})

    def test_interrupted_import_is_repairable_without_reusing_prior_approvals(self):
        old=evidence();new=evidence(datetime.now(timezone.utc)+timedelta(seconds=1))
        with materialize(empty_state()) as work:
            intel.write_json(work.service.workspace/'verified.json',old)
            reviews=intel.review_template(old)
            reviews['reviews'][0].update(approved=True,acknowledge_subtree=True,
                reviewer='operator',reason='Explicit review of domain and subtree impact')
            intel.write_json(work.service.workspace/'reviews.json',reviews)
            # Simulate power loss after replacing only the first of the pair.
            intel.write_json(work.service.workspace/'verified.json',new)
            self.store.save(0,work.export())
        pre=self.post('cloud/evidence/preview',{'verified':new}).json()
        result=self.post('cloud/evidence',{'verified':new,'confirm':'IMPORT_VERIFIED',
            'context_revision':pre['context_revision'],'fingerprint':pre['fingerprint']})
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()['imported'])
        self.assertFalse(self.client.get('/api/ops/reviews').json()['items'][0]['approved'])
        self.assertTrue(any('evidence-archive' in x for x in self.store.load()['state']['files']))

    def test_same_valid_evidence_is_idempotent_and_preserves_approval(self):
        verified=evidence()
        with materialize(empty_state()) as work:
            intel.write_json(work.service.workspace/'verified.json',verified)
            reviews=intel.review_template(verified)
            reviews['reviews'][0].update(approved=True,acknowledge_subtree=True,
                reviewer='operator',reason='Explicit review of domain and subtree impact')
            intel.write_json(work.service.workspace/'reviews.json',reviews)
            self.store.save(0,work.export())
        pre=self.post('cloud/evidence/preview',{'verified':verified}).json()
        result=self.post('cloud/evidence',{'verified':verified,'confirm':'IMPORT_VERIFIED',
            'context_revision':pre['context_revision'],'fingerprint':pre['fingerprint']})
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()['already_current'])
        self.assertTrue(self.client.get('/api/ops/reviews').json()['items'][0]['approved'])

    def test_gui_build_requires_the_review_set_it_displayed(self):
        verified=evidence()
        with materialize(empty_state()) as work:
            intel.write_json(work.service.workspace/'verified.json',verified)
            reviews=intel.review_template(verified)
            reviews['reviews'][0].update(approved=True,acknowledge_subtree=True,
                reviewer='operator',reason='Explicit review of domain and subtree impact')
            intel.write_json(work.service.workspace/'reviews.json',reviews)
            self.store.save(0,work.export())
        current=self.client.get('/api/ops/reviews').json()
        request={'fingerprint':current['fingerprint'],'confirm_replacement':True,
                 'acknowledge_user_notice':True}
        self.assertEqual(self.post('build',request).status_code,409)
        self.assertEqual(self.post('build',{**request,'review_set_revision':'f'*64}).status_code,409)
        response=self.post('build',{**request,'review_set_revision':current['review_set_revision']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['rules'],1)
