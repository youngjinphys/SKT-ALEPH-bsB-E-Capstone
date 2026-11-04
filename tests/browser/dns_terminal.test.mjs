import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {terminalResultParts} from '../../apps/web/src/lib/dns-terminal-results.ts';
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


test('the Pi DNS example is explicit and disconnected from captured experiments',()=>{
 const source=fs.readFileSync(path.join(web,'src/components/ServerDnsObservation.tsx'),'utf8');
 const slide=JSON.parse(fs.readFileSync(path.join(web,'capstone/data/slides/09-bypass.json'),'utf8'));
 assert.ok(source.includes('공개 DNS 별도 관측 · 1.1.1.1 · 명령 옵션 일부 생략'));
 assert.ok(source.includes('PI DNS · ILLUSTRATION'));
 const wrapper=fs.readFileSync(path.join(web,'src/components/EditorialVisual.tsx'),'utf8');
 assert.ok(wrapper.includes('className="diagram-panel dns-evidence-dashboard" aria-label="DNS 질의 기록과 예시"'));
 assert.ok(source.includes('예시 · 미실행'));
 assert.ok(source.includes('Pi DNS 차단 예시 · 미실행'));
 assert.ok(source.includes('data-command-display="illustration"'));
 assert.ok(source.includes('dig @${PI_DNS} block.test A'));
 assert.ok(source.includes('<Transcript text={exampleOutput}/>'));
 assert.ok(source.includes('publicDns?"captured":"illustration"'));
 assert.ok(source.includes('NXDOMAIN (expected)'));
 assert.doesNotMatch(source,/block-test-loopback|blockedQuery|block\.phases|ISOLATED LOOPBACK|CAPTURED|type Transport|type Route|setTransport|setRoute|onKeyDown/);
 const visible=JSON.stringify([slide.title,slide.subtitle,slide.points,slide.presentation,slide.reading,slide.visual]);
 assert.ok(visible.includes('미실행'));
 assert.doesNotMatch(visible,/\b(?:TCP|UDP)\b|격리 차단 검증|12개 질의/);
 assert.ok(!slide.sources.includes('block-test-loopback-20261104'));
 const manuscript=fs.readFileSync(path.join(web,'docs/presentation/final-20min-scenario.md'),'utf8');
 const schedule=manuscript.split('\n').find(line=>line.startsWith('| 09 |'));
 assert.ok(schedule.includes('Pi DNS 미실행 예시'));
 assert.ok(schedule.includes(slide.title.replace('\n',' ')));
 assert.doesNotMatch(manuscript,/block\.test[^\n]*격리 차단 실험/);
 assert.doesNotMatch(manuscript,/07:37 UTC|12개 질의가 기대 응답과 일치/);
 const registry=JSON.parse(fs.readFileSync(path.join(web,'capstone/data/sources.json'),'utf8'));
 assert.ok(registry['block-test-loopback-20261104']); // Historical evidence remains intact.
});

test('Google answer display preserves the separate stored public IPv4 record',()=>{
 const capturePath=path.join(web,'public/capstone/evidence/google-dns-observation.json');
 const observed=JSON.parse(fs.readFileSync(capturePath,'utf8'));
 assert.equal(observed.domain,'google.com');
 assert.equal(observed.resolver,'1.1.1.1');
 assert.equal(observed.status,'NOERROR');
 assert.ok(observed.answers.length>0);
 assert.ok(observed.answers.every(line=>/^google\.com\. \d+ IN A (?:\d{1,3}\.){3}\d{1,3}$/.test(line)));
 const source=fs.readFileSync(path.join(web,'src/components/ServerDnsObservation.tsx'),'utf8');
 assert.ok(source.includes('google-dns-observation.json'));
 assert.ok(source.includes('공개 DNS 별도 관측'));
 assert.equal(JSON.parse(fs.readFileSync(path.join(web,'capstone/data/slides/09-bypass.json'),'utf8')).reading.source,'https://github.com/youngjinphys/SKT-ALEPH-bsB-E-Capstone/blob/bf7d1d613b2bd5824454fe9d3695711e7b13eb11/apps/web/public/capstone/evidence/google-dns-observation.json');
});

test('highlighting preserves response bytes and marks result codes and answer counts',()=>{
 const cases=[
  [';; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 10534',[['NXDOMAIN','negative']]],
  [';; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, ADDITIONAL: 1',[['ANSWER: 0','negative']]],
  ['status: NOERROR; ANSWER: 6',[['NOERROR','success'],['ANSWER: 6','success']]],
  ['status: SERVFAIL; ANSWER: 0',[['ANSWER: 0','negative']]],
  ['literal NOERRORsuffix and prefixNXDOMAIN · 한글\n',[]]
 ];
 for(const [text,highlights] of cases){
  const parts=terminalResultParts(text);
  assert.equal(parts.map(part=>part.text).join(''),text);
  assert.deepEqual(parts.filter(part=>part.tone).map(part=>[part.text,part.tone]),highlights);
 }
 const fixture=JSON.parse(fs.readFileSync(path.join(web,'public/capstone/evidence/block-test-loopback-20261104.json'),'utf8'));
 for(const phase of fixture.phases)for(const query of phase.queries){
  assert.equal(terminalResultParts(query.stdout).map(part=>part.text).join(''),query.stdout);
 }
 const style=fs.readFileSync(path.join(web,'src/components/server-dns-observation.css'),'utf8');
 assert.ok(style.includes('font-weight:700'));
 assert.ok(style.includes('text-decoration:underline'));
 assert.ok(style.includes('.dns-terminal-result[data-result]{color:CanvasText;background:Canvas}'));
 const luminance=hex=>[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
 const palettes=[...style.matchAll(/data-result=(\w+)\]\{color:#([a-f0-9]{6});background:#([a-f0-9]{6})/g)];
 assert.equal(palettes.length,2);
 for(const [,name,foreground,background] of palettes){
  const a=luminance(foreground),b=luminance(background);
  assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=7,`${name} token contrast`);
 }
});
