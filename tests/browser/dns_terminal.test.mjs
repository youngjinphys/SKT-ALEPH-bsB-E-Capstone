import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const web=path.resolve(import.meta.dirname,'../../apps/web');
const capture=JSON.parse(fs.readFileSync(path.join(web,'public/capstone/evidence/dns-terminal-20261104.json'),'utf8'));
const extract=fs.readFileSync(path.join(web,'public/capstone/evidence/dns-query-20261104.txt'),'utf8');

test('terminal records preserve all eight captured query conditions and their public evidence',()=>{
 assert.equal(capture.queries.length,8);
 assert.equal(new Set(capture.queries.map(q=>q.id)).size,8);
 assert.equal(capture.sourceSha256,'a3157ec2f8e70c55dda4223073be38b937850ed8bed4d6d0e89e58e96462e87b');
 assert.deepEqual(capture.queries.map(q=>q.queryMs),[9,68,1,70,8,41,1,65]);
 assert.deepEqual(capture.queries.map(q=>q.answerCount),[1,6,1,6,2,2,2,2]);
 for(const q of capture.queries){
  assert.ok(extract.includes(`UTC: ${q.timestamp}\n$ ${q.command}\nexit=${q.exitCode}; status=NOERROR; flags=qr rd ra; ANSWER=${q.answerCount}; SERVER=${q.route==='private'?'${PRIVATE_DNS}':'[SYSTEM_STUB]'}; transport=${q.transport}`));
  assert.equal(q.answers.length,q.answerCount);
  assert.ok(q.header.includes('opcode: QUERY, status: NOERROR'));
  assert.equal(q.flags,`;; flags: qr rd ra; QUERY: 1, ANSWER: ${q.answerCount}, AUTHORITY: 0, ADDITIONAL: 1`);
  assert.ok(q.answers.every(line=>new RegExp(`^${q.domain.replaceAll('.','\\.')}\\. \\d+ IN A \\[REDACTED\\]$`).test(line)));
  assert.ok(Number.isInteger(q.queryMs)&&q.queryMs>=0);
 }
 assert.doesNotMatch(JSON.stringify(capture),/\b(?:\d{1,3}\.){3}\d{1,3}\b|\/home\/|fe80:/);
});

test('scoped Korean web fonts retain licensed, verified bytes and required glyph coverage',()=>{
 const dir=path.join(web,'public/fonts/dns-ui');
 const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json'),'utf8'));
 const coverage=new Set(manifest.unicode);
 for(const relative of manifest.coverageInputs){
  for(const char of fs.readFileSync(path.join(web,relative),'utf8')){
   if(/[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]/u.test(char))assert.ok(coverage.has(char.codePointAt(0)),`Missing ${char}`);
  }
 }
 for(const font of manifest.fonts){
  const bytes=fs.readFileSync(path.join(dir,font.file));
  assert.equal(bytes.subarray(0,4).toString(),'wOFF');
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),font.sha256);
 }
 const license=fs.readFileSync(path.join(dir,'LICENSE.txt'),'utf8');
 assert.ok(license.includes('SIL OPEN FONT LICENSE Version 1.1'));
 assert.ok(license.includes('PERMISSION & CONDITIONS'));
 assert.ok(license.includes('DISCLAIMER'));
});

test('stored terminal choices use native buttons without capturing arrow keys',()=>{
 const source=fs.readFileSync(path.join(web,'src/components/ServerDnsObservation.tsx'),'utf8');
 assert.doesNotMatch(source,/onKeyDown|role="radio|tabIndex|fetch\(|eval\(/);
});


test('the simplified display keeps the Google capture and never fabricates block.test output',()=>{
 const source=fs.readFileSync(path.join(web,'src/components/ServerDnsObservation.tsx'),'utf8');
 const style=fs.readFileSync(path.join(web,'src/components/server-dns-observation.css'),'utf8');
 const slide=JSON.parse(fs.readFileSync(path.join(web,'capstone/data/slides/09-bypass.json'),'utf8'));
 assert.ok(source.includes('data-command-display="summary"'));
 assert.ok(source.includes('명령·응답 일부 생략'));
 assert.ok(source.includes('질의 미실행 · 차단 미확인'));
 assert.ok(source.includes('recorded?"captured":"unverified"'));
 assert.doesNotMatch(source,/type Transport|type Route|setTransport|setRoute|record\.server|google\.server|dns-terminal-routes/);
 assert.doesNotMatch(style,/dns-terminal-routes/);
 assert.equal(capture.queries.filter(q=>q.domain==='block.test').length,0);
 const visible=JSON.stringify([slide.title,slide.subtitle,slide.points,slide.presentation,slide.reading,slide.visual]);
 assert.doesNotMatch(visible,/example\.com|기본 DNS|사설 DNS|UDP|TCP/);
 assert.ok(visible.includes('미검증'));
});
