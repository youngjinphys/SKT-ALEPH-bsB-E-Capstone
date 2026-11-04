import base64,hashlib,hmac,json,os,time,unittest,uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from cloud.app import app
from cloud.state import MemoryStore,StorageUnavailable,Conflict
from cloud.assets import assets

ORIGIN='https://aleph-protective-dns.foggy-elf-5146.chatgpt.site'
# Valid production Sites host contains a dot; explicit configured origin remains required.
KEY=b'0123456789abcdef0123456789abcdef'
def b64(raw):return base64.urlsafe_b64encode(raw).decode().rstrip('=')
class SitesBridge(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'CAPSTONE_SITES_BRIDGE_ORIGIN':ORIGIN,'CAPSTONE_SITES_BRIDGE_SECRET':b64(KEY),'CAPSTONE_OPS_ALLOWED_EMAILS':'owner@example.org'})
        self.env.start();self.addCleanup(self.env.stop);self.client=TestClient(app)
    def headers(self,path='/api/ops/session',method='GET',body=b'',**changes):
        now=int(time.time())
        claims=dict(v=1,iss=ORIGIN,aud='aleph-ops',email='owner@example.org',iat=now,exp=now+30,jti=str(uuid.uuid4()),method=method,path=path,body_sha256=hashlib.sha256(body).hexdigest())
        claims.update(changes);encoded=b64(json.dumps(claims,separators=(',',':')).encode())
        return {'X-Aleph-Sites-Assertion':encoded,'X-Aleph-Sites-Signature':b64(hmac.digest(KEY,encoded.encode(),'sha256')),'Origin':ORIGIN,'Sec-Fetch-Site':'same-origin','Content-Type':'application/json'}
    def test_valid_session_does_not_need_db_or_cookie_auth(self):
        with patch('cloud.state.SupabaseStore',side_effect=AssertionError('DB used')):
            response=self.client.get('/api/ops/session',headers=self.headers())
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['email'],'owner@example.org')
    def test_invalid_claims_and_nonoperator(self):
        variants=[({'iss':'https://evil.chatgpt.site'},401),({'aud':'other'},401),({'email':'other@example.org'},403),({'path':'/api/ops/overview'},401),({'method':'POST'},401),({'body_sha256':'0'*64},401),({'exp':int(time.time())-1},401),({'iat':int(time.time())+10},401),({'exp':int(time.time())+100},401),({'v':True},401),({'jti':'bad'},401)]
        for changes,status in variants:
            with self.subTest(changes=changes):self.assertEqual(self.client.get('/api/ops/session',headers=self.headers(**changes)).status_code,status)
    def test_forged_signature_and_mixed_auth_never_fall_back(self):
        for changes in ({'X-Aleph-Sites-Signature':'a'*43},{'Cookie':'__Host-capstone_at=valid-existing-token'},{'Authorization':'Bearer bogus'},{'X-Aleph-Sites-Assertion':'bad'}):
            headers={**self.headers(),**changes}
            with patch('cloud.app.require_operator',side_effect=AssertionError('fallback')):
                self.assertEqual(self.client.get('/api/ops/session',headers=headers).status_code,401)
    def test_partial_headers_and_duplicate_headers(self):
        headers=self.headers();headers.pop('X-Aleph-Sites-Signature')
        self.assertEqual(self.client.get('/api/ops/session',headers=headers).status_code,401)
        headers=list(self.headers().items());headers.append(('X-Aleph-Sites-Assertion','bad'))
        self.assertEqual(self.client.get('/api/ops/session',headers=headers).status_code,401)
    def test_query_and_unknown_paths_and_pin_are_not_bridge_routes(self):
        for path in ['/api/ops/session?x=1','/api/ops/test-auth','/api/ops/unknown']:
            self.assertEqual(self.client.get(path,headers=self.headers(path=path.split('?')[0])).status_code,401)
    def test_posts_bind_bytes_origin_and_use_durable_replay_protection(self):
        body=b'{"domain":"example.org"}';path='/api/ops/evaluate';headers=self.headers(path,'POST',body)
        with patch('cloud.sites_bridge.SupabaseStore') as store,patch('cloud.app.get_store',return_value=MemoryStore()):
            store.return_value.rpc.side_effect=[True,False]
            self.assertNotEqual(self.client.post(path,content=body,headers=headers).status_code,401)
            self.assertEqual(self.client.post(path,content=body,headers=headers).status_code,401)
            self.assertEqual(store.return_value.rpc.call_count,2)
        for changes in ({'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'},{'Origin':''}):
            self.assertEqual(self.client.post(path,content=body,headers={**headers,**changes}).status_code,403)
        self.assertEqual(self.client.post(path,content=b'{}',headers=headers).status_code,401)
    def test_signed_write_preserves_audited_actor_and_state(self):
        path='/api/ops/engine'
        body=json.dumps({'policy_version':'sites-test','warn_threshold':70,'admin_blocked_domains':[], 'approved_malicious_domains':[],'official_domains':[],'score_sources':['reviewed']}).encode()
        store=MemoryStore()
        with patch('cloud.sites_bridge.SupabaseStore') as replay,patch('cloud.app.get_store',return_value=store):
            replay.return_value.rpc.return_value=True
            response=self.client.post(path,content=body,headers=self.headers(path,'POST',body))
        self.assertEqual(response.status_code,200,response.text)
        snapshot=store.load()
        self.assertEqual(snapshot['revision'],1)
        self.assertIn('owner@example.org',snapshot['state']['files']['workspace/audit.jsonl'])

    def test_replay_store_outage_fails_closed(self):
        path='/api/ops/evaluate';body=b'{}'
        with patch('cloud.sites_bridge.SupabaseStore',side_effect=StorageUnavailable('outage')):
            self.assertEqual(self.client.post(path,content=body,headers=self.headers(path,'POST',body)).status_code,503)
    def test_replay_store_conflict_is_controlled_failure(self):
        path='/api/ops/evaluate';body=b'{}'
        with patch('cloud.sites_bridge.SupabaseStore',side_effect=Conflict('upstream conflict')):
            response=self.client.post(path,content=body,headers=self.headers(path,'POST',body))
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error'],'Sites replay protection unavailable')
    def test_non_ascii_raw_path_is_controlled_denial(self):
        from starlette.requests import Request
        from fastapi import HTTPException
        from cloud.sites_bridge import verify
        headers=[(k.lower().encode(),v.encode()) for k,v in self.headers().items()]
        request=Request({'type':'http','method':'GET','path':'/api/ops/session','raw_path':b'/api/ops/\xff',
                         'query_string':b'','headers':headers,'scheme':'https','server':('testserver',443)})
        with self.assertRaises(HTTPException) as caught:verify(request,b'')
        self.assertEqual(caught.exception.status_code,401)
        self.assertEqual(caught.exception.detail,'Invalid Sites assertion')

    def test_sites_asset_variant_preserves_ordinary_auth(self):
        ordinary=assets();sites=assets('sites')
        self.assertIn('cloud-pin-form',ordinary[0]);self.assertIn('/api/oauth',ordinary[0]);self.assertIn('cloudPinStatus',ordinary[2])
        self.assertNotIn('cloud-pin-form',sites[0]);self.assertNotIn('/api/oauth',sites[0]);self.assertNotIn('cloudPin',sites[2]);self.assertNotIn('/api/auth',sites[2])
        self.assertIn('target="_top"',sites[0]);self.assertIn('/signin-with-chatgpt?return_to=%2Fdashboard',sites[0]);self.assertIn('sessionEpoch',sites[2]);self.assertIn('cloudOperation',sites[2])
        self.assertIn('?surface=sites',self.client.get('/dashboard?surface=sites').text)
        self.assertIn('sites-session',self.client.get('/dashboard/assets/console.js?surface=sites').text)
