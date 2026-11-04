"""Read-only storage diagnostics and authenticated mutation provenance."""
import json
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from cloud.app import app
from cloud.state import MemoryStore, StorageUnavailable, Conflict

ORIGIN='https://skt-aleph-capstone.vercel.app'
CONFIG={'policy_version':'audit-v1','warn_threshold':70,'admin_blocked_domains':[],
        'approved_malicious_domains':[],'official_domains':[],'score_sources':['reviewed']}

class OperatorDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.store=MemoryStore()
        self.client=TestClient(app)
        self.auth=patch('cloud.app.require_operator',return_value='operator@example.org')
        self.backend=patch('cloud.app.get_store',return_value=self.store)
        self.env=patch.dict(os.environ,{'CAPSTONE_SITE_ORIGIN':ORIGIN})
        for item in (self.auth,self.backend,self.env):item.start();self.addCleanup(item.stop)

    def test_capacity_inspection_is_read_only_and_contains_no_private_file_contents(self):
        state={'format':1,'files':{'workspace/verified.json':'{"private":"sensitive-url"}'}}
        self.store.save(0,state)
        response=self.client.get('/api/ops/cloud/storage')
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['file_count'],1)
        self.assertEqual(result['state'],'NORMAL')
        self.assertEqual(result['revision'],1)
        self.assertFalse(result['automatic_cleanup'])
        self.assertNotIn('sensitive-url',response.text)
        self.assertNotIn('verified.json',response.text)
        self.assertEqual(self.store.load()['revision'],1)

    def test_capabilities_do_not_depend_on_storage_availability(self):
        with patch('cloud.app.get_store',side_effect=StorageUnavailable('outage')):
            result=self.client.get('/api/ops/capabilities')
            self.assertEqual(result.status_code,200,result.text)
            self.assertTrue(result.json()['storage_diagnostics'])
            health=self.client.get('/api/ops/cloud/storage')
            self.assertEqual(health.status_code,503)
            self.assertNotIn('bytes_used',health.json())

    def test_mutation_records_verified_operator_identity_in_same_commit(self):
        saved=self.client.post('/api/ops/engine',json=CONFIG,headers={'Origin':ORIGIN})
        self.assertEqual(saved.status_code,200,saved.text)
        state=self.store.load()
        events=[json.loads(line) for line in state['state']['files']['workspace/audit.jsonl'].splitlines()]
        committed=[x for x in events if x['event']=='cloud_operator_committed']
        self.assertEqual(len(committed),1)
        self.assertEqual(committed[0]['actor'],'operator@example.org')
        self.assertEqual(committed[0]['action'],'engine')
        self.assertEqual(committed[0]['state_revision'],state['revision'])
        self.assertNotIn('policy_version',committed[0])
        self.assertNotIn('Authorization',str(committed[0]))

    def test_read_only_evaluation_does_not_create_a_mutation_record(self):
        self.client.post('/api/ops/engine',json=CONFIG,headers={'Origin':ORIGIN})
        before=self.store.load()
        result=self.client.post('/api/ops/evaluate',json={'domain':'example.org'},headers={'Origin':ORIGIN})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.store.load(),before)

    def test_rejected_compare_and_swap_persists_no_successful_actor_record(self):
        before=self.store.load()
        with patch.object(self.store,'save',side_effect=Conflict('racing writer')):
            result=self.client.post('/api/ops/engine',json=CONFIG,headers={'Origin':ORIGIN})
        self.assertEqual(result.status_code,409)
        self.assertEqual(self.store.load(),before)

    def test_diagnostics_still_require_operator_authentication(self):
        from fastapi import HTTPException
        with patch('cloud.app.require_operator',side_effect=HTTPException(401,'login required')):
            self.assertEqual(self.client.get('/api/ops/cloud/storage').status_code,401)
            self.assertEqual(self.client.get('/api/ops/capabilities').status_code,401)

if __name__=='__main__':unittest.main()
