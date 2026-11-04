import os,sys,tempfile,threading,json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import cloud
from cloud.state import MemoryStore,empty_state,materialize
from cloud.operations import import_evidence,trust_key,publish
from policy_server import intel
from policy_server.console import ConsoleService,handler_for
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from aleph_policy_sync.snapshot import sign_policy,canonical,public_key_id
from aleph_policy_sync.telemetry import signed_report
from aleph_policy_sync.metrics import blank_metrics
from cloud import app as ca
import uvicorn
now=datetime.now(timezone.utc)
urls=['https://secure-account-review.online/login','https://payment-verify.example.net/login','https://shared-tenant.github.io/verify','https://delivery-check.example.org/login']
col=intel.collect_urls(('\n'.join(urls)+'\n').encode(),source='openphish',fetched_at=now)
verified=intel.verify_collected(col,'synthetic-key',checked_at=now,fetch=lambda *a,**k: json.dumps({'threats':[{'url':u,'threatTypes':['SOCIAL_ENGINEERING']} for u in urls],'cacheDuration':'1800s'}).encode())
with materialize(empty_state()) as w:
    # Seed fixtures directly so changes to import API contracts don't affect fixture setup.
    intel.write_json(w.service.workspace/'verified.json', verified)
    intel.write_json(w.service.workspace/'reviews.json', intel.review_template(verified))
    state=w.service.reviews(); item=state['items'][0]
    w.service.update_review(dict(id=item['id'],revision=item['revision'],fingerprint=state['fingerprint'],approved=True,acknowledge_subtree=True,reviewer='Fixture operator',reason='Synthetic acceptance data: verified URL and SUBTREE scope'))
    d=w.service.build(dict(fingerprint=state['fingerprint'],confirm_replacement=True,acknowledge_user_notice=True))
    key=Ed25519PrivateKey.generate();pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    trust_key(w,dict(role='policy',public_key=pem,confirm='TRUST_PUBLIC_KEY'))
    envelope=sign_policy(w.service.download(d['draft']),key,target='edge-69',sequence=12)
    publish(w,dict(device_id='edge-69',envelope=envelope,expected_sequence=0,ack_withdrawals=False,ack_key_rotation=False))
    second=sign_policy(w.service.download(d['draft']),key,target='edge-70',sequence=5)
    publish(w,dict(device_id='edge-70',envelope=second,expected_sequence=0,ack_withdrawals=False,ack_key_rotation=False))
    for idx,(dev,label,ip) in enumerate([('edge-69','연구실 · 기본 DNS','192.168.7.69'),('edge-70','실습망 · 보조 DNS','192.168.7.70')]):
        k=Ed25519PrivateKey.generate();pk=k.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        kid=trust_key(w,dict(role='node',public_key=pk,confirm='TRUST_PUBLIC_KEY'))['key_id']
        w.service.register_node(dict(device_id=dev,label=label,dns_address=ip,key_id=kid))
        if idx==0:
            p=dict(format=2,type='aleph-dns-node-report',device_id=dev,report_sequence=7,reported_at=now.isoformat(),dns_address=ip,policy_sequence=12,policy_sha256=envelope['payload']['policy_sha256'],applied_at=now.isoformat(),attestation='ATTESTED',probe=dict(domain=item['domain'],udp=True,tcp=True,baseline=True))
            # Synthetic signed aggregates exist only in this isolated fixture.
            p['format']=4
            for sample in range(36):
                at=now-timedelta(seconds=(35-sample)*60)
                m=blank_metrics(extended=True)
                m['host'].update(uptime_s=3600+sample*60,boot_id='a'*16,load_1m=round(.2+(sample%8)*.07,3),memory_used_pct=34+sample%9,disk_used_pct=28.5)
                m['system'].update(cpu_total_ticks=10000+sample*1000,cpu_idle_ticks=5000+sample*400,cpu_count=2,interface='eth0',ifindex=2,rx_bytes=100000+sample*60000,tx_bytes=50000+sample*30000,rx_errors=0,tx_errors=0,rx_dropped=sample//10,tx_dropped=0,local_dns_udp_ms=3+sample%4,local_dns_tcp_ms=7+sample%4,upstream_dns_udp_ms=14+sample%5,upstream_dns_tcp_ms=24+sample%7,dns_attempts=4,dns_failures=0,probe_domain='example.org')
                m['cache']={'hits':10000+sample*90,'misses':1000+sample*15,'evictions':sample,'insertions':sample*10,'size':150}
                m['policy']={'valid_until':(now+timedelta(minutes=5)).isoformat(),'active_blocks':1}
                for transport in ('udp','tcp'):
                    for qtype in ('A','AAAA'):
                        m['checks'].append(dict(target='local',transport=transport,qtype=qtype,rcode=3,elapsed_ms=round(1.4+(sample%7)*.3+(1.8 if transport=='tcp' else 0),2),outcome='response'))
                p.update(report_sequence=sample+1,reported_at=at.isoformat(),applied_at=at.isoformat(),metrics=m)
                w.service.nodes.receive(signed_report(p,k,now=at),now=at)
    snap=w.export()
if os.getenv('ALEPH_BROWSER_EXPIRED_REVIEWS')=='1':
    # A separate offline acceptance variant: retain the signed fixture feed,
    # but age its source evidence to exercise explicit source exclusion.
    old=now-timedelta(minutes=10)
    verified['checked_at']=old.isoformat()
    for row in verified['entries']:
        row.update(checked_at=old.isoformat(),valid_until=(old+timedelta(minutes=5)).isoformat())
    reviews=intel.review_template(verified)
    reviews['reviews'][0].update(approved=True,acknowledge_subtree=True,reviewer='Fixture operator',
        reason='Synthetic stale approval with reviewed whole subtree impact')
    snap['files']['workspace/verified.json']=json.dumps(verified)
    snap['files']['workspace/reviews.json']=json.dumps(reviews)
store=MemoryStore();store.save(0,snap)
ca.get_store=lambda:store
ca.require_operator=lambda request:'fixture@example.org'
os.environ['CAPSTONE_SITE_ORIGIN']='http://127.0.0.1:18766'
@ca.app.get('/api/auth')
def auth(): return {'authenticated':True,'user':{'email':'fixture@example.org'}}
@ca.app.get('/')
def home():return {'fixture':True}
# Local: same state with an isolated fake collector.
tmp=tempfile.TemporaryDirectory(); root=Path(tmp.name)
for rel,content in snap['files'].items():
 p=root/rel;p.parent.mkdir(parents=True,mode=0o700,exist_ok=True);p.write_text(content);p.chmod(0o600)
keyfile=root/'token';keyfile.write_text('a'*48);keyfile.chmod(0o600)
class Collector:
 def request(self,action,**fields):
  meta=dict(run='20261103T000000Z-0123456789',fingerprint=intel.verification_fingerprint(verified),checked_at=verified['checked_at'],verified=len(urls),review_proposals=len(urls),unassigned_expressions=0)
  if action=='status':return dict(state='SUCCESS',latest=meta,cooldown_seconds=0,requested_at=None,completed_at=None,error_code=None)
  if action=='snapshot':return dict(**meta,verified_snapshot=verified)
  return dict(state='RUNNING',accepted=True)
svc=ConsoleService(root/'workspace',keyfile,feed_root=root/'feed',device='edge-69',trust_dir=root/'policy-trust',node_trust_dir=root/'node-trust',refresh_client=Collector())
server=ThreadingHTTPServer(('127.0.0.1',18765),handler_for(svc,'http://127.0.0.1:18765'))
threading.Thread(target=server.serve_forever,daemon=True).start()
uvicorn.run(ca.app,host='127.0.0.1',port=18766,log_level='warning')
