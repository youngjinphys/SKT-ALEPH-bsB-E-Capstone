import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const raw=readFileSync(new URL('../../apps/policy-server/src/policy_server/console_quality.py',import.meta.url),'utf8');
const source=raw.split("JS = r'''")[1].split("\n'''")[0];
const ctx=vm.createContext({console});vm.runInContext(source,ctx);
const summarize=(points,target='local')=>JSON.parse(JSON.stringify(ctx.qualitySummary(points,target)));
const point=(seq,udp,tcp,extra={})=>({sequence:seq,at:seq*60000,received_at:seq*60000,boot_id:'a',gap:false,hourly_sample:false,
  dns_attempts:2,dns_failures:Number(udp===null)+Number(tcp===null),local_dns_udp_ms:udp,local_dns_tcp_ms:tcp,...extra});
test('empty and legacy metrics never become zero-success quality',()=>{
  const s=summarize([{sequence:1,at:1,received_at:1,gap:true}]);
  assert.equal(s.attempts,0);assert.equal(s.failurePct,null);assert.equal(s.udp.p95,null);
});
test('failure rate is weighted by attempts, not mean of percentages; coarse samples excluded',()=>{
  const s=summarize([point(1,10,null),point(2,20,25,{dns_attempts:4,dns_failures:0,upstream_dns_udp_ms:12,upstream_dns_tcp_ms:15}),
    point(3,9000,9000,{hourly_sample:true})]);
  assert.equal(s.attempts,6);assert.equal(s.failures,1);assert.equal(s.failurePct,100/6);
  assert.equal(s.excludedHourly,1);assert.equal(s.udp.n,2);assert.equal(s.udp.p95,20);
  assert.equal(s.udp.variationMs,10);assert.equal(s.tcp.variationMs,null);
});
test('variation never bridges gaps, reboot, failed probe, or nonmonotonic time',()=>{
  for(const changed of [{gap:true},{boot_id:'b'},{at:1,received_at:1}]){
    assert.equal(summarize([point(1,10,11),point(2,30,31,changed)]).udp.variationMs,null);
  }
  const s=summarize([point(1,10,11),point(2,null,null),point(3,30,31)]);
  assert.equal(s.udp.variationMs,null);assert.equal(s.udp.n,2);
});
test('transport and local/upstream summaries cannot mix observations',()=>{
 const p=point(1,10,11,{dns_attempts:4,dns_failures:1,upstream_dns_udp_ms:50,upstream_dns_tcp_ms:null});
 assert.equal(summarize([p],'upstream').udp.p50,50);assert.equal(summarize([p],'upstream').tcp.n,0);
});
