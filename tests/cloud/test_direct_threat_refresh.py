"""Mocked external-provider end-to-end flow, zero production network contact."""
from unittest.mock import patch
from datetime import datetime,timezone
import json,os,unittest
from fastapi.testclient import TestClient
from cloud.app import app
from cloud.state import MemoryStore,materialize
from policy_server import intel

class CloudThreatFlow(unittest.TestCase):
    def setUp(self):
        self.store=MemoryStore()
        for name,value in [('cloud.app.get_store',self.store),('cloud.app.require_operator','operator@example.org')]:
            p=patch(name,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'CAPSTONE_SITE_ORIGIN':'https://skt-aleph-capstone.vercel.app',
                                  'SAFE_BROWSING_API_KEY':'test-key',
                                  'ALEPH_OPENPHISH_SOURCE_ALLOWED':'true'})
        p.start();self.addCleanup(p.stop)
        self.client=TestClient(app);self.headers={'Origin':'https://skt-aleph-capstone.vercel.app'}
        self.ack={'accept_openphish_terms':True,'ack_url_disclosure':True,'ack_noncommercial':True}
        self.url='https://synthetic-phishing.example.org/login'
    def fetch(self,url,**kwargs):
        if url==intel.OPENPHISH:return (self.url+'\n').encode()
        self.assertTrue(url.startswith(intel.GOOGLE+'?'))
        self.assertEqual(kwargs['headers']['x-goog-api-key'],'test-key')
        return json.dumps({'threats':[{'url':self.url,'threatTypes':['SOCIAL_ENGINEERING']}],
                           'cacheDuration':'300s'}).encode()
    def test_refresh_is_pending_until_confirmed_import(self):
        with patch('cloud.intel_refresh.intel.get_https',side_effect=self.fetch) as getter:
            r=self.client.post('/api/ops/intel/refresh',json=self.ack,headers=self.headers)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(getter.call_count,2)
        self.assertEqual(r.json()['state'],'SUCCESS')
        state=self.client.get('/api/ops/intel').json()
        self.assertEqual(state['latest']['review_proposals'],1)
        self.assertNotIn(self.url,json.dumps(state))
        self.assertTrue(self.client.get('/api/ops/reviews').json()['missing'])
        body={k:state['latest'][k] for k in ('run','fingerprint')}
        body.update(review_revision=state['review_revision'],
                    context_revision=state['context_revision'],confirm='IMPORT_VERIFIED')
        committed=self.client.post('/api/ops/intel/import',json=body,headers=self.headers)
        self.assertEqual(committed.status_code,200,committed.text)
        self.assertFalse(self.client.get('/api/ops/reviews').json()['items'][0]['approved'])
        self.assertEqual(self.store.load()['revision'],3)
        self.assertEqual(self.client.post('/api/ops/intel/import',json=body,headers=self.headers).status_code,409)
    def test_disabled_is_explicit_and_never_calls_provider(self):
        with patch.dict(os.environ,{'SAFE_BROWSING_API_KEY':'','ALEPH_OPENPHISH_SOURCE_ALLOWED':''}):
            self.assertEqual(self.client.get('/api/ops/intel').json()['state'],'NOT_CONFIGURED')
            with patch('cloud.intel_refresh.intel.get_https') as getter:
                reply=self.client.post('/api/ops/intel/refresh',json=self.ack,headers=self.headers)
            self.assertEqual(reply.status_code,503);getter.assert_not_called()
            self.assertEqual(self.store.load()['revision'],0)
    def test_acknowledgements_cooldown_and_private_errors(self):
        self.assertEqual(self.client.post('/api/ops/intel/refresh',
                         json={**self.ack,'ack_noncommercial':False},headers=self.headers).status_code,422)
        with patch('cloud.intel_refresh.intel.get_https',side_effect=self.fetch):
            self.assertEqual(self.client.post('/api/ops/intel/refresh',
                             json=self.ack,headers=self.headers).status_code,200)
        before=self.store.load()['revision']
        with patch('cloud.intel_refresh.intel.get_https') as getter:
            self.assertEqual(self.client.post('/api/ops/intel/refresh',
                             json=self.ack,headers=self.headers).status_code,409)
        getter.assert_not_called();self.assertEqual(before,self.store.load()['revision'])
    def test_failed_provider_does_not_mutate_reviews_or_leak_error(self):
        with patch('cloud.intel_refresh.intel.get_https',
                   side_effect=intel.IntelError('PRIVATE_KEY_OR_URL')):
            r=self.client.post('/api/ops/intel/refresh',json=self.ack,headers=self.headers)
        self.assertEqual(r.status_code,503,r.text)
        self.assertNotIn('PRIVATE_KEY_OR_URL',r.text)
        self.assertEqual(self.client.get('/api/ops/intel').json()['state'],'ERROR')
        self.assertTrue(self.client.get('/api/ops/reviews').json()['missing'])
