import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

class CloudContract(unittest.TestCase):
    def test_cloud_adapter_exists_without_replacing_local_engine(self):
        self.assertTrue((ROOT/'cloud/app.py').is_file(), 'a real serverless adapter is required')
    def test_snapshot_paths_are_confined(self):
        from cloud.state import validate_state
        for name in ('../token','workspace/../../secret','/etc/passwd','workspace/.nodes.lock','workspace/a\\b'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_state({'format':1,'files':{name:'x'}})
        validate_state({'format':1,'files':{'workspace/reviews.json':'{}'}})
    def test_compare_and_swap_does_not_overwrite_parallel_update(self):
        from cloud.state import MemoryStore, Conflict
        store=MemoryStore(); a=store.load();b=store.load()
        store.save(a['revision'], {'format':1,'files':{'workspace/engine-config.json':'{}'}})
        with self.assertRaises(Conflict):store.save(b['revision'],b['state'])
        self.assertEqual(store.load()['revision'],1)
    def test_materialized_workspace_uses_existing_compiler(self):
        from cloud.state import materialize, empty_state
        with materialize(empty_state()) as state:
            self.assertEqual(state.service.engine_config(),{'configured':False,'config':None})
            cfg={'policy_version':'cloud-test','warn_threshold':70,'admin_blocked_domains':['blocked.example.org'], 'approved_malicious_domains':[],'official_domains':[],'score_sources':['reviewed']}
            state.service.configure_engine(cfg)
            proposed=state.service.evaluate({'domain':'blocked.example.org'})
            self.assertEqual(proposed['proposal']['scope'],'EXACT')
            self.assertFalse(proposed['enforcing'])
            snap=state.export()
        with materialize(snap) as state:
            self.assertEqual(state.service.engine_config()['config'],cfg)
    def test_empty_operator_allowlist_denies_confirmed_google_account(self):
        from cloud.security import operator_allowed
        self.assertFalse(operator_allowed('someone@example.org',{}))
        self.assertTrue(operator_allowed('OWNER@EXAMPLE.ORG',{'CAPSTONE_OPS_ALLOWED_EMAILS':'owner@example.org'}))
        self.assertFalse(operator_allowed('other@example.org',{'CAPSTONE_OPS_ALLOWED_EMAILS':'owner@example.org'}))
    def test_unauthenticated_and_cross_origin_requests_fail_closed(self):
        from fastapi.testclient import TestClient
        from cloud.app import app
        c=TestClient(app)
        self.assertEqual(c.get('/dashboard').status_code,200)
        self.assertIn('관제',c.get('/dashboard').text)
        self.assertIn('/api/oauth',c.get('/dashboard').text)
        self.assertEqual(c.get('/api/ops/overview').status_code,401)
        self.assertEqual(c.get('/api/ops/analytics').status_code,401)
        self.assertEqual(c.post('/api/ops/build',json={},headers={'Origin':'https://evil.example'}).status_code,403)
    def test_dashboard_does_not_send_operator_bearer_secrets(self):
        from cloud.assets import assets
        html,css,js=assets()
        self.assertIn('/dashboard/assets/console.js',html)
        self.assertIn('href="/"',html)
        self.assertNotIn('Bearer "+token',js)
        self.assertIn('credentials:"same-origin"',js)
    def test_scoped_authenticated_write_and_read_use_durable_store(self):
        from fastapi.testclient import TestClient
        from cloud.app import app
        from cloud.state import MemoryStore
        store=MemoryStore()
        with patch('cloud.app.require_operator',return_value='owner@example.org'),patch('cloud.app.get_store',return_value=store),patch.dict(os.environ,{'CAPSTONE_SITE_ORIGIN':'https://skt-aleph-capstone.vercel.app'}):
            c=TestClient(app)
            self.assertEqual(c.get('/api/ops/overview').status_code,200)
            stats=c.get('/api/ops/analytics')
            self.assertEqual(stats.status_code,200)
            self.assertEqual(stats.json()['nodes'],[])
            self.assertEqual(store.load()['revision'],0)
            config={'policy_version':'cloud-test','warn_threshold':70,'admin_blocked_domains':['blocked.example.org'],'approved_malicious_domains':[],'official_domains':[],'score_sources':['reviewed']}
            result=c.post('/api/ops/engine',json=config,headers={'Origin':'https://skt-aleph-capstone.vercel.app'})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(c.get('/api/ops/engine').json()['config'],config)
            self.assertEqual(store.load()['revision'],1)
    def test_machine_ingress_does_not_accept_unsigned_health(self):
        from fastapi.testclient import TestClient
        from cloud.app import app
        from cloud.state import MemoryStore
        with patch('cloud.app.get_store',return_value=MemoryStore()):
            result=TestClient(app).post('/v1/nodes/report',json={'device_id':'edge-69','status':'healthy'})
            self.assertEqual(result.status_code,422,result.text)
    def test_no_private_policy_is_served_without_valid_signed_envelope(self):
        from fastapi.testclient import TestClient
        from cloud.app import app
        from cloud.state import MemoryStore
        with patch('cloud.app.get_store',return_value=MemoryStore()):
            result=TestClient(app).get('/v1/policies/edge-69/current.json')
            self.assertEqual(result.status_code,404,result.text)

if __name__=='__main__':unittest.main()
