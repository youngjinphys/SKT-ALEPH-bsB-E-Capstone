"""Synthetic aggregate observations; no client histories or production data."""
import copy,json,math,sys,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps'/app/'src') for app in ('policy-server','policy-sync','dns-agent')]
try:
    from aleph_policy_sync.metrics import blank_metrics,validate_metrics,read_counter_response
    from policy_server.analytics import append_history,history_points,COLUMNS
except ImportError:
    blank_metrics=validate_metrics=read_counter_response=append_history=history_points=None

class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(blank_metrics),'aggregate collector/schema missing')
        self.now=datetime.now(timezone.utc)
    def test_unknown_is_null_and_no_client_or_query_history_fields(self):
        m=blank_metrics();validate_metrics(m)
        self.assertIsNone(m['cache']);self.assertIsNone(m['host']['memory_used_pct'])
        self.assertEqual(m['checks'],[])
        for key in ('client_ip','domains','queries','hostname'):
            self.assertNotIn(key,m)
        m['client_ip']='192.168.1.20'
        with self.assertRaises(ValueError):validate_metrics(m)
    def test_nonfinite_boolean_and_bounds_are_rejected(self):
        for bad in (float('nan'),float('inf'),True,-1,101):
            m=blank_metrics();m['host']['memory_used_pct']=bad
            with self.subTest(value=bad),self.assertRaises(ValueError):validate_metrics(m)
        m=blank_metrics();m['checks']=[{'target':'local','transport':'udp','qtype':'A','rcode':3,'elapsed_ms':1.5,'outcome':'response'}]
        validate_metrics(m)
        m['checks']*=2
        with self.assertRaises(ValueError):validate_metrics(m)
    def test_counter_dns_parser_matches_transaction_question_and_type(self):
        import struct
        question=b'\x04hits\x04bind\x00'+struct.pack('!HH',16,3)
        data=b'\x041234';answer=b'\xc0\x0c'+struct.pack('!HHIH',16,3,0,len(data))+data
        packet=struct.pack('!HHHHHH',24,0x8000,1,1,0,0)+question+answer
        self.assertEqual(read_counter_response(packet,24,question,'hits.bind'),1234)
        for bad in (packet[:8],packet[:-1],packet.replace(b'hits',b'evil'),packet[:2]+b'\x82\x00'+packet[4:]):
            with self.subTest(bad=bad),self.assertRaises((ValueError,RuntimeError)):
                read_counter_response(bad,24,question,'hits.bind')
    def payload(self,seq,at,hits=100,misses=20,boot='a'*16):
        m=blank_metrics();m['host'].update(uptime_s=seq*60,boot_id=boot)
        m['cache']={'hits':hits,'misses':misses,'evictions':0,'insertions':0,'size':150}
        return {'format':3,'report_sequence':seq,'reported_at':at.isoformat(),'attestation':'ATTESTED','metrics':m}
    def test_history_retries_bounds_and_no_false_rates_on_reset(self):
        h=None;start=self.now-timedelta(minutes=100)
        for i in range(100):
            p=self.payload(i+1,start+timedelta(minutes=i),100+i*10,20+i*5)
            h=append_history(h,p,start+timedelta(minutes=i,seconds=1))
        self.assertLessEqual(len(h['recent']),48);self.assertLessEqual(len(h['hourly']),24)
        rows=history_points(h,self.now)
        self.assertAlmostEqual(rows[-1]['cache_lookups_per_s'],15/60)
        self.assertAlmostEqual(rows[-1]['cache_hit_pct'],100*10/15,places=3)
        before=copy.deepcopy(h);h=append_history(h,p,start+timedelta(minutes=99,seconds=1))
        self.assertEqual(h,before)
        p=self.payload(101,self.now,2,1,'b'*16);h=append_history(h,p,self.now)
        self.assertIsNone(history_points(h,self.now)[-1]['cache_lookups_per_s'])
    def test_history_missing_gaps_and_expiry_are_not_zeros(self):
        h=append_history(None,self.payload(1,self.now-timedelta(minutes=10)),self.now-timedelta(minutes=10))
        h=append_history(h,self.payload(2,self.now,200,40),self.now)
        rows=history_points(h,self.now)
        self.assertIsNone(rows[-1]['cache_hit_pct']);self.assertTrue(rows[-1]['gap'])
        self.assertIsNone(rows[-1]['udp_ms'])
        self.assertEqual(history_points(h,self.now+timedelta(days=2)),[])

    def test_worst_case_histories_fit_current_snapshot_limits(self):
        h=None
        for i in range(1600):
            at=self.now-timedelta(seconds=(1599-i)*60)
            p=self.payload(i+1,at,hits=2**50+i*10,misses=2**49+i)
            h=append_history(h,p,at)
        size=len(json.dumps({'received_at':self.now.isoformat(),'history':h,'signed':{}},indent=2).encode())
        self.assertLess(size,131072)
        # Reserve room for active evidence/policies in the existing 8MiB store.
        self.assertLess(size*64,6*1024*1024)

    def test_counter_collection_is_opt_in_and_partials_stay_unknown(self):
        from aleph_policy_sync.metrics import collect_metrics
        from unittest.mock import Mock
        reader=Mock(return_value=12)
        self.assertIsNone(collect_metrics('192.168.7.69',counter_reader=reader)['cache'])
        reader.assert_not_called()
        reader.side_effect=[12,OSError('disabled'),14,15,150]
        m=collect_metrics('192.168.7.69',cache_enabled=True,counter_reader=reader)
        self.assertEqual(m['cache']['hits'],12)
        self.assertIsNone(m['cache']['misses'])
        self.assertEqual(reader.call_count,5)

    def test_signed_v3_report_bound_and_legacy_versions_remain_valid(self):
        from aleph_policy_sync.telemetry import signed_report,validate_payload,MAX_REPORT_BYTES
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        base=dict(format=3,type='aleph-dns-node-report',device_id='edge-69',report_sequence=1,
            reported_at=self.now.isoformat(),dns_address='192.168.7.69',policy_sequence=None,
            policy_sha256=None,applied_at=None,attestation='NO_POLICY',
            probe=dict(domain=None,udp=None,tcp=None,baseline=None),metrics=blank_metrics())
        self.assertLess(len(signed_report(base,Ed25519PrivateKey.generate())),MAX_REPORT_BYTES)
        malformed=copy.deepcopy(base);malformed['metrics']['raw_queries']=['private.example']
        with self.assertRaises(ValueError):validate_payload(malformed)
        for version in (1,2):
            legacy=copy.deepcopy(base);legacy['format']=version;legacy.pop('metrics')
            if version==1:legacy['probe'].pop('baseline')
            validate_payload(legacy)

if __name__=='__main__':unittest.main()
