import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {buildReferenceIndex,markdownLinks} from '../../apps/web/src/lib/references.ts';
const manuscript='# 발표자 참고 · 예상 질문과 답변\n\n## 첫 질문\n\n설명 [같은 원문](https://example.org/doc#second).\n\n## 다음 질문\n\n추가 [문서](https://example.org/other).';
const slide={id:'example',title:'첫 화면\n제목',sources:['primary','alias']};
const sources={primary:{label:'원문',url:'https://example.org/doc#first',note:'조건'},alias:{label:'같은 문서',url:'https://example.org/doc'}};
test('references preserve slide numbers, full source labels, dedup and manuscript questions',()=>{
 const result=buildReferenceIndex([slide],sources,manuscript);
 assert.equal(result.entries.length,2);assert.deepEqual(result.entries[0].slides,[1]);
 assert.deepEqual(result.slideIndex[0].references,['reference-1']);
 assert.equal(result.slideIndex[0].title,'첫 화면 제목');
 assert.equal(result.questions.length,2);assert.equal(result.questions[1].title,'다음 질문');
 assert.equal(result.entries[1].label,'문서');assert.deepEqual(result.entries[1].slides,[]);
});
test('missing source, absent or empty manuscript section and unsafe URL fail clearly',()=>{
 assert.throws(()=>buildReferenceIndex([slide],{},manuscript),/Missing reference/);
 assert.throws(()=>buildReferenceIndex([],{},'# 잘못된 문서'),/missing/);
 assert.throws(()=>buildReferenceIndex([],{},'# 발표자 참고 · 예상 질문과 답변'),/empty/);
 assert.throws(()=>buildReferenceIndex([{...slide,sources:['bad']}],{bad:{label:'bad',url:'javascript:alert(1)'}},manuscript),/HTTPS/);
 assert.deepEqual(markdownLinks('[bad](javascript:alert(1))'),[]);
});
test('current deck includes every active-slide citation and all manuscript Q&A, without archived slides',()=>{
 const root=new URL('../../apps/web/',import.meta.url);
 const read=path=>JSON.parse(fs.readFileSync(new URL(path,root),'utf8'));
 const records=read('capstone/data/slides.index.json').map(file=>read('capstone/data/slides/'+file));
 const sequence=read('capstone/data/sequence.json');const registry=read('capstone/data/sources.json');
 const active=sequence.slides.map(({id})=>records.find(slide=>slide.id===id));
 const text=fs.readFileSync(new URL('docs/presentation/final-20min-scenario.md',root),'utf8');
 const result=buildReferenceIndex(active,registry,text);
 assert.equal(result.slideIndex.length,15);assert.ok(result.entries.length>25);assert.ok(result.questions.length>10);
 assert.ok(!result.slideIndex.some(slide=>sequence.archived.includes(slide.id)));
 const bibliography=active.find(slide=>slide.id==='sources');
 assert.equal(active.at(-1).id,'sources');assert.equal(sequence.mainSlideCount,14);
 assert.equal(bibliography.sources.length,40);
 const grouped=bibliography.referenceGroups.flatMap(group=>group.keys);
 assert.deepEqual(new Set(grouped),new Set(bibliography.sources));
 assert.equal(grouped.length,40);
 assert.ok(!grouped.includes("block-test-loopback-20261104"));
 assert.ok(grouped.includes("pi-dns-block-20261105"));
 assert.ok(!fs.existsSync(new URL('src/app/capstone/references/page.tsx',root)));
 const deckSource=fs.readFileSync(new URL('src/components/SlideDeck.tsx',root),'utf8');
 assert.ok(!deckSource.includes('/capstone/references'));
 assert.ok(deckSource.includes('href="/dashboard"'));
 assert.ok(deckSource.includes('at<mainSlideCount&&deck[at].id!=="opening"'));
 const expectedQuestions=text.split('# 발표자 참고 · 예상 질문과 답변')[1].match(/^## /gm).length;
 assert.equal(result.questions.length,expectedQuestions);
 for(const [i,slide] of active.entries())for(const key of slide.sources){
  assert.ok(grouped.includes(key),`Bibliography omits ${slide.id}/${key}`);
  const url=new URL(registry[key].url);url.hash='';
  const entry=result.entries.find(entry=>{const u=new URL(entry.url);u.hash='';return u.href===url.href;});
  assert.ok(entry,`${slide.id}/${key}`);assert.ok(entry.slides.includes(i+1));
 }
});

test('requested pipeline label changes without removing manual approval boundaries',()=>{
 const diagrams=JSON.parse(fs.readFileSync(new URL('../../apps/web/capstone/data/diagrams.json',import.meta.url),'utf8'));
 assert.equal(diagrams.policyPipeline.lab[1].owner,'정책기반 위험도 판정');
 assert.equal(diagrams.policyPipeline.lab[1].label,'검토·승인');
 assert.match(diagrams.policyPipeline.lab[1].detail,/SUBTREE/);
 assert.match(diagrams.policyPipeline.lab[2].detail,/관리자 게시/);
});
