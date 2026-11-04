import copy,json,unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import cloud
from cloud.state import MemoryStore,materialize,empty_state

class Enrollment(unittest.TestCase):
    def test_public_descriptor_proves_key_possession_and_preserves_private_key(self):
        from aleph_policy_sync.enrollment import make_enrollment,validate_enrollment
        key=Ed25519PrivateKey.generate()
        request=make_enrollment(key,'test-node','192.168.7.69','Test node')
        checked=validate_enrollment(request)
        self.assertEqual(checked['device_id'],'test-node')
        self.assertNotIn('PRIVATE KEY',json.dumps(request))
        changed=copy.deepcopy(request);changed['payload']['dns_address']='192.168.7.70'
        with self.assertRaises(ValueError):validate_enrollment(changed)

    def test_atomic_operator_enrollment_and_idempotency(self):
        from aleph_policy_sync.enrollment import make_enrollment
        from cloud.enrollment import preview_enrollment,enroll
        request=make_enrollment(Ed25519PrivateKey.generate(),'test-node','192.168.7.69','Test node')
        with materialize(empty_state()) as w:
            prior=w.export()
            preview=preview_enrollment(w,{'enrollment':request})
            self.assertEqual(prior,w.export())
            result=enroll(w,{'enrollment':request,'expected_key_id':preview['key_id'],'confirm':'ENROLL_NODE'})
            self.assertTrue(result['registered'])
            self.assertEqual(w.service.node_states()[0]['state'],'NO_REPORT')
            self.assertTrue(enroll(w,{'enrollment':request,'expected_key_id':preview['key_id'],'confirm':'ENROLL_NODE'})['already_registered'])

    def test_conflicting_device_cannot_be_silently_replaced(self):
        from aleph_policy_sync.enrollment import make_enrollment
        from cloud.enrollment import enroll
        with materialize(empty_state()) as w:
            for n in range(2):
                req=make_enrollment(Ed25519PrivateKey.generate(),'same-node','192.168.7.69','Test node')
                body={'enrollment':req,'expected_key_id':req['key_id'],'confirm':'ENROLL_NODE'}
                if not n:enroll(w,body)
                else:
                    original=w.export()
                    with self.assertRaises(ValueError):enroll(w,body)
                    self.assertEqual(original,w.export())

    def test_enrollment_api_requires_operator_and_origin(self):
        from fastapi.testclient import TestClient
        from cloud.app import app
        c=TestClient(app)
        self.assertIn(c.post('/api/ops/cloud/enroll',json={}).status_code,(401,403))
        self.assertEqual(c.post('/v1/nodes/report',json={}).status_code,422)
