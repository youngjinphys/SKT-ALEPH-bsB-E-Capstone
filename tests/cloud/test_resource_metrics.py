"""Offline resource metrics: no simulated samples ever written to production."""
import copy, os, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import cloud
from aleph_policy_sync import metrics
from policy_server import analytics

class ResourceMetrics(unittest.TestCase):
    def test_extended_metrics_have_explicit_missing_values(self):
        self.assertIn('system', metrics.blank_metrics(extended=True))
        self.assertIsNone(metrics.blank_metrics(extended=True)['system']['rx_bytes'])

    def test_linux_ticks_exclude_guest_and_interface_is_explicit(self):
        from aleph_policy_sync.system_metrics import collect_system
        with tempfile.TemporaryDirectory() as folder:
            proc=Path(folder)/'proc'; net=Path(folder)/'net'; proc.mkdir(); net.mkdir()
            (proc/'stat').write_text('cpu 100 20 30 400 50 6 7 8 500 900\ncpu0 1\ncpu1 1\n')
            iface=net/'eth0'; (iface/'statistics').mkdir(parents=True)
            (iface/'ifindex').write_text('2\n')
            for key,val in {'rx_bytes':1200,'tx_bytes':600,'rx_errors':0,'tx_errors':0,'rx_dropped':1,'tx_dropped':0}.items():
                (iface/'statistics'/key).write_text(str(val))
            data=collect_system(proc=proc,net=net,interface='eth0')
            self.assertEqual(data['cpu_total_ticks'],621)
            self.assertEqual(data['cpu_idle_ticks'],450)
            self.assertEqual(data['cpu_count'],2)
            self.assertEqual(data['rx_bytes'],1200)
            self.assertEqual(data['interface'],'eth0')
            self.assertIsNone(collect_system(proc=proc,net=net)['rx_bytes'])
            with self.assertRaises(ValueError): collect_system(interface='../../etc')

    def test_nonfinite_bool_and_inconsistent_counters_rejected(self):
        from aleph_policy_sync.system_metrics import blank_system,validate_system
        for key,value in [('cpu_total_ticks',True),('rx_bytes',float('nan')),('local_dns_udp_ms',float('inf'))]:
            item=blank_system();item[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_system(item)
        item=blank_system();item.update(cpu_total_ticks=10,cpu_idle_ticks=20)
        with self.assertRaises(ValueError): validate_system(item)
        item=blank_system();item['hostname']='private-host'
        with self.assertRaises(ValueError): validate_system(item)

    def test_rates_and_cpu_do_not_bridge_restart_or_interface_change(self):
        from aleph_policy_sync.system_metrics import blank_system
        now=datetime.now(timezone.utc)
        def payload(seq,total,idle,rx,boot='a'*16,iface='eth0'):
            m=metrics.blank_metrics(extended=True)
            m['host'].update(uptime_s=seq*60,boot_id=boot)
            m['system'].update(cpu_total_ticks=total,cpu_idle_ticks=idle,cpu_count=2,
                interface=iface,ifindex=2,rx_bytes=rx,tx_bytes=rx,rx_errors=seq,tx_errors=0,rx_dropped=0,tx_dropped=0)
            return {'reported_at':(now+timedelta(seconds=(seq-1)*60)).isoformat(),'report_sequence':seq,'attestation':'NO_POLICY','metrics':m}
        h=analytics.append_history(None,payload(1,1000,400,1000),now)
        h=analytics.append_history(h,payload(2,1200,500,7000),now+timedelta(seconds=60))
        pts=analytics.history_points(h,now+timedelta(seconds=61))
        self.assertIsNone(pts[0]['cpu_used_pct'])
        self.assertEqual(pts[-1]['cpu_used_pct'],50)
        self.assertEqual(pts[-1]['rx_bytes_per_s'],100)
        h=analytics.append_history(h,payload(3,1400,600,8000,boot='b'*16),now+timedelta(seconds=120))
        self.assertIsNone(analytics.history_points(h,now+timedelta(seconds=121))[-1]['rx_bytes_per_s'])
        h=analytics.append_history(h,payload(4,1600,700,9000,boot='b'*16,iface='ens3'),now+timedelta(seconds=180))
        self.assertIsNone(analytics.history_points(h,now+timedelta(seconds=181))[-1]['rx_bytes_per_s'])

    def test_legacy_history_migrates_without_inventing_cpu_or_network(self):
        now=datetime.now(timezone.utc)
        row=[int(now.timestamp()*1000)]*2+[1,60,'a'*16,1,20,30]+[None]*7+[0,0,None,None,'NO_POLICY']
        old={'format':1,'recent':[row],'hourly':[row]}
        points=analytics.history_points(old,now)
        self.assertEqual(len(points),1)
        self.assertIsNone(points[0]['cpu_used_pct'])
        self.assertIsNone(points[0]['rx_bytes_per_s'])
        self.assertEqual(points[0]['memory_used_pct'],20)

    def test_probe_failure_is_not_zero_latency_or_packet_loss(self):
        from aleph_policy_sync.system_metrics import collect_quality,blank_system
        s=blank_system()
        def fail(*args,**kwargs):raise TimeoutError('timeout')
        collect_quality(s,'192.168.7.69',None,resolver=fail)
        self.assertEqual(s['dns_attempts'],2)
        self.assertEqual(s['dns_failures'],2)
        self.assertIsNone(s['local_dns_udp_ms'])
        self.assertNotIn('packet_loss',s)

    def test_hourly_last_observation_retains_ingest_rates(self):
        # Align to an hour so the first retained bucket has multiple samples.
        # A wall-clock start at minute 59 can retain only the initial unknown
        # rate; that valid startup case is covered separately above.
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        history=None
        for i in range(180):
            m=metrics.blank_metrics(extended=True)
            m['host'].update(uptime_s=3600+i*60,boot_id='a'*16)
            m['system'].update(cpu_total_ticks=1000+i*100,cpu_idle_ticks=400+i*40,cpu_count=2)
            at=now+timedelta(minutes=i)
            payload={'reported_at':at.isoformat(),'report_sequence':i+1,'attestation':'NO_POLICY','metrics':m}
            history=analytics.append_history(history,payload,at)
        points=analytics.history_points(history,now+timedelta(hours=3))
        coarse=[p for p in points if p['hourly_sample']]
        self.assertTrue(coarse)
        self.assertTrue(all(p['cpu_used_pct']==60 for p in coarse))
        self.assertLessEqual(len(history['recent']),48)
        self.assertLessEqual(len(history['hourly']),24)

    def test_resource_discontinuity_does_not_invent_rate(self):
        now=datetime.now(timezone.utc)
        def frame(seq,offset,total,idle,uptime):
            m=metrics.blank_metrics(extended=True);m['host'].update(uptime_s=uptime,boot_id='a'*16)
            m['system'].update(cpu_total_ticks=total,cpu_idle_ticks=idle,cpu_count=2)
            return {'reported_at':(now+timedelta(seconds=offset)).isoformat(),'report_sequence':seq,'attestation':'NO_POLICY','metrics':m}
        h=analytics.append_history(None,frame(1,0,1000,400,60),now)
        h=analytics.append_history(h,frame(2,60,1100,390,120),now+timedelta(seconds=60))
        self.assertIsNone(analytics.history_points(h,now+timedelta(seconds=60))[-1]['cpu_used_pct'])
        h=analytics.append_history(h,frame(3,600,2000,1000,660),now+timedelta(seconds=600))
        self.assertIsNone(analytics.history_points(h,now+timedelta(seconds=600))[-1]['cpu_used_pct'])
