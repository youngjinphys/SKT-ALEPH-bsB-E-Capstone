import importlib.util
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import cloud
from cloud import app as ca
from fastapi.testclient import TestClient
from aleph_policy_sync import telemetry

class ReceiverDiagnostics(unittest.TestCase):
    def test_public_capabilities_do_not_touch_private_state(self):
        with patch.object(ca, 'get_store', side_effect=AssertionError('must not load DB')):
            reply = TestClient(ca.app).get('/v1/nodes/report')
        self.assertEqual(reply.status_code, 200)
        body=reply.json()
        self.assertEqual(body['service'],'aleph-signed-node-receiver')
        self.assertEqual(body['formats'],[1,2,3,4])
        self.assertIs(body['enrollment_required'],True)
        self.assertEqual(body['metrics_format'],4)
        self.assertEqual(body['storage'],'not_checked')
        self.assertIn('no-store',reply.headers['cache-control'])
        self.assertNotIn('nodes',body)

    def test_health_check_rejects_redirect_html_and_clock_skew(self):
        from aleph_policy_sync.receiver import check_receiver
        now=datetime(2026,11,4,tzinfo=timezone.utc)
        body={'service':'aleph-signed-node-receiver','formats':[1,2,3,4],
              'metrics_format':4,'enrollment_required':True,'storage':'not_checked',
              'server_time':now.isoformat()}
        with patch('aleph_policy_sync.receiver.fetch_health',return_value=body):
            result=check_receiver('https://skt-aleph-capstone.vercel.app/v1/nodes/report',now=now)
            self.assertTrue(result['reachable'])
            self.assertEqual(result['clock_skew_s'],0)
        with patch('aleph_policy_sync.receiver.fetch_health',return_value={'html':'login'}):
            with self.assertRaisesRegex(ValueError,'receiver'):
                check_receiver('https://skt-aleph-capstone.vercel.app/v1/nodes/report',now=now)
        body['server_time']=(now+timedelta(minutes=5)).isoformat()
        with patch('aleph_policy_sync.receiver.fetch_health',return_value=body):
            with self.assertRaisesRegex(ValueError,'clock'):
                check_receiver('https://skt-aleph-capstone.vercel.app/v1/nodes/report',now=now)
        for url in ['http://example.org/v1/nodes/report','https://example.org/v1/nodes/report?token=secret',
                    'https://u:p@example.org/v1/nodes/report','https://example.org/other']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                check_receiver(url,now=now)

    def test_interface_inference_is_unique_not_a_guess(self):
        path=Path(__file__).resolve().parents[2]/'scripts/deploy/connect-node-dashboard.py'
        spec=importlib.util.spec_from_file_location('connector',path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        data=[{'ifname':'ens3','addr_info':[{'local':'192.168.7.69'}]}]
        self.assertEqual(mod.resolve_interface(data,'192.168.7.69',None),'ens3')
        self.assertEqual(mod.resolve_interface(data,'192.168.7.69','ens3'),'ens3')
        for observed,configured in [(data,'eth0'),([],None),(data+[{**data[0],'ifname':'ens4'}],None)]:
            with self.assertRaises(ValueError):mod.resolve_interface(observed,'192.168.7.69',configured)

    def test_interface_counter_sample_rejects_hotplug_race(self):
        from aleph_policy_sync import system_metrics as sm
        indexes=iter(['2','7'])
        def read(path,limit=131072):
            if path.name=='stat':return 'cpu 10 0 0 20 0 0 0 0\ncpu0 1\n'
            if path.name=='ifindex':return next(indexes)
            return '100'
        with patch.object(sm,'_read',side_effect=read):
            sample=sm.collect_system(interface='eth0')
        self.assertIsNone(sample['rx_bytes'])
        self.assertIsNone(sample['ifindex'])
        self.assertEqual(sample['cpu_total_ticks'],30)

    def test_signed_legacy_node_reports_upgrade_requirement_without_losing_identity(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from aleph_policy_sync.enrollment import make_enrollment
        from cloud.enrollment import enroll
        from cloud.state import materialize, empty_state
        key=Ed25519PrivateKey.generate();now=datetime.now(timezone.utc).isoformat()
        descriptor=make_enrollment(key,'fixture-node','192.168.7.69','Fixture node')
        with materialize(empty_state()) as work:
            enroll(work,{'enrollment':descriptor,'expected_key_id':descriptor['key_id'],'confirm':'ENROLL_NODE'})
            payload={'format':2,'type':'aleph-dns-node-report','device_id':'fixture-node','report_sequence':1,
                     'reported_at':now,'dns_address':'192.168.7.69','policy_sequence':None,'policy_sha256':None,
                     'applied_at':None,'attestation':'NO_POLICY','probe':{'domain':None,'udp':None,'tcp':None,'baseline':None}}
            work.service.receive_node_report(telemetry.signed_report(payload,key))
            node=work.service.analytics()['nodes'][0]
            self.assertEqual(node['report_format'],2)
            self.assertEqual(node['device_id'],'fixture-node')
            self.assertIsNone(node['metrics'])
            self.assertEqual(node['state'],'NO_POLICY')
