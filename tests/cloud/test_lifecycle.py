from datetime import datetime,timezone
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from cloud.state import empty_state,materialize,MemoryStore
from cloud.operations import trust_key,import_evidence,preview_evidence,publish
from policy_server import intel
from aleph_policy_sync.snapshot import sign_policy,canonical
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

class Lifecycle(unittest.TestCase):
 def test_independent_signer_and_persistent_publication(self):
  key=Ed25519PrivateKey.generate()
  pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
  now=datetime.now(timezone.utc);url='https://malicious-example-domain.online/login'
  collected=intel.collect_urls((url+'\n').encode(),source='local-openphish',fetched_at=now)
  verified=intel.verify_collected(collected,'fake-test-key',checked_at=now,fetch=Mock(return_value=json.dumps({'threats':[{'url':url,'threatTypes':['SOCIAL_ENGINEERING']}],'cacheDuration':'300s'}).encode()))
  with materialize(empty_state()) as work:
   trust_key(work,{'role':'policy','public_key':pem,'confirm':'TRUST_PUBLIC_KEY'})
   with self.assertRaises(ValueError):trust_key(work,{'role':'node','public_key':pem,'confirm':'TRUST_PUBLIC_KEY'})
   preview=preview_evidence(work,{'verified':verified})
   import_evidence(work,{'verified':verified,'confirm':'IMPORT_VERIFIED','context_revision':preview['context_revision'],'fingerprint':preview['fingerprint']})
   reviews=work.service.reviews();item=reviews['items'][0]
   work.service.update_review({'fingerprint':reviews['fingerprint'],'id':item['id'],'revision':item['revision'],'approved':True,'acknowledge_subtree':True,'reviewer':'Test reviewer','reason':'Confirmed a synthetic test threat and all subdomain impacts'})
   draft=work.service.build({'fingerprint':reviews['fingerprint'],'confirm_replacement':True,'acknowledge_user_notice':True})
   raw=work.service.download(draft['draft']);envelope=sign_policy(raw,key,target='edge-69',sequence=1)
   args={'device_id':'edge-69','envelope':envelope,'expected_sequence':0,'ack_withdrawals':False,'ack_key_rotation':False}
   published=publish(work,args)
   self.assertIsNone(published['dns_applied'])
   with self.assertRaises(ValueError):publish(work,args)
   stored=work.export()
  with materialize(stored) as work:
   state=work.service.deployment(include_rules=True)
   self.assertEqual(state['state'],'SIGNED_FILE_VERIFIED')
   self.assertEqual(state['sequence'],1)
   self.assertEqual(state['rules'][0]['domain'],'malicious-example-domain.online')
   self.assertIsNone(state['dns_applied'])
  from fastapi.testclient import TestClient
  from cloud.app import app
  store=MemoryStore();store.save(0,stored)
  with patch('cloud.app.get_store',return_value=store):
   response=TestClient(app).get('/v1/policies/edge-69/current.json')
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['payload']['sequence'],1)
   self.assertIn('no-store',response.headers['cache-control'])
 def test_private_signing_material_is_never_imported(self):
  key=Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
  with materialize(empty_state()) as work:
   with self.assertRaises(ValueError):trust_key(work,{'role':'policy','public_key':key,'confirm':'TRUST_PUBLIC_KEY'})
if __name__=='__main__':unittest.main()
