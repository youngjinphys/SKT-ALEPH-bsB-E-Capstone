import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const web=path.resolve(import.meta.dirname,'../../apps/web');
const record=JSON.parse(fs.readFileSync(path.join(web,'public/capstone/evidence/pi-dns-block-20261105.json'),'utf8'));

test('recorded Pi DNS queries distinguish observations from policy attribution',()=>{
 assert.match(record.scope,/independent device identity and active policy not verified/);
 assert.match(record.interpretation,/NXDOMAIN alone cannot establish/);
 assert.match(record.active_policy,/not verified/);
 assert.match(record.raw_private_capture_sha256,/^[a-f0-9]{64}$/);
 assert.ok(Date.parse(record.started_at)<=Date.parse(record.finished_at));
 for(const [queries,domain,status,count] of [[record.block_queries,'block.test','NXDOMAIN',0],[record.control_queries,'google.com','NOERROR',6]]){
  assert.deepEqual(new Set(queries.map(q=>q.transport)),new Set(['UDP','TCP']));
  for(const q of queries){
   assert.equal(q.domain,domain);assert.equal(q.qtype,'A');assert.equal(q.exit_code,0);
   assert.equal(q.rcode,status);assert.equal(q.answer_count,count);
   assert.ok(q.command.includes('@${PI_DNS}'));assert.ok(q.command.includes(domain));
   assert.equal(q.command.includes('+tcp'),q.transport==='TCP');
   assert.ok(Date.parse(record.started_at)<=Date.parse(q.started_at));
   assert.ok(Date.parse(q.started_at)<=Date.parse(q.finished_at));
   assert.ok(Date.parse(q.finished_at)<=Date.parse(record.finished_at));
   if(domain==='block.test'){
    assert.equal(q.private_address_redactions,0);
    assert.match(q.stdout,/status: NXDOMAIN/);assert.match(q.stdout,/ANSWER: 0/);
    assert.equal(q.stderr,'');
   }
  }
 }
 assert.doesNotMatch(JSON.stringify(record),/\b(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d/);
});
