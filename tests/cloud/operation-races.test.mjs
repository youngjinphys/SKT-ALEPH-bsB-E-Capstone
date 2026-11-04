import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source=readFileSync(new URL('../../cloud/actions.js',import.meta.url),'utf8')
  .replace(/\ncloudConnect\(\);\s*$/,'\n');
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function harness(responder=async()=>({importable:true,verified:1,fresh:1,review_proposals:1,
  fingerprint:'a'.repeat(64),context_revision:'b'.repeat(64),checked_at:'2026-11-03T00:00:00Z'})){
  const elements=new Map(),events=new Map(),forms=new Map(),docEvents=new Map();
  const element=()=>({value:'',files:[],checked:false,hidden:false,disabled:false,textContent:'',dataset:{},
    setAttribute(){},removeAttribute(){},append(){},replaceChildren(){},reset(){}});
  const context=vm.createContext({console,
    document:{querySelector:()=>element(),addEventListener:(k,f)=>docEvents.set(k,f)},
    $:id=>{if(!elements.has(id)){const el=element();el.addEventListener=(k,f)=>{
      const key=id+':'+k;if(!events.has(key))events.set(key,[]);events.get(key).push(f);
    };elements.set(id,el);}return elements.get(id);},
    bindAsyncForm:(id,fn)=>forms.set(id,fn),node:()=>element(),showText(){},fmt:x=>x,
    api:async(path,body)=>{context.calls.push({path,body});return responder(path,body);},
    calls:[],errors:[],displayError:e=>{if(!e.stale)context.errors.push(e.message);},toast(){},
    loadReviews:async()=>{},loadDeployment:async()=>{},confirmOperation:async()=>true,
    window:{location:{assign(){}}},fetch:async()=>({ok:false,status:401}),
    staleRequest:()=>Object.assign(Error('STALE_SESSION'),{stale:true})});
  vm.runInContext(`let token='cookie-session';let sessionEpoch=1;let viewEpoch=1;
    let currentView='reviews';let selectedReview=null;
    function lock(){sessionEpoch++;token=null;}
    function unlock(){sessionEpoch++;token='cookie-session';}`,context);
  vm.runInContext(source,context);
  const event=(id,kind)=>{for(const fn of events.get(id+':'+kind)||[])fn({});};
  return {context,elements,events,forms,docEvents,event,run:code=>vm.runInContext(code,context)};
}

test('reauthentication while reading evidence cannot submit a prior-session file',async()=>{
  const pending=deferred(),h=harness();
  h.context.$('cloud-evidence').files=[{size:50,text:()=>pending.promise}];
  const job=h.forms.get('cloud-evidence-form')();
  h.run('lock();unlock()');
  pending.resolve('{"old_session":true}');await job;
  assert.equal(h.context.calls.length,0,'obsolete upload reached current authenticated API');
  assert.equal(h.run('cloudEvidencePreview'),null);
});

test('changing evidence file during an in-flight preview invalidates its response',async()=>{
  const response=deferred(),h=harness(()=>response.promise);
  h.context.$('cloud-evidence').files=[{size:5,text:async()=>'{"v":1}'}];
  const job=h.forms.get('cloud-evidence-form')();
  await new Promise(resolve=>setImmediate(resolve));
  h.context.$('cloud-evidence').files=[{size:5,text:async()=>'{"v":2}'}];h.event('cloud-evidence','change');
  response.resolve({importable:true,verified:1,fresh:1,review_proposals:1,fingerprint:'a'.repeat(64)});
  await job;
  assert.equal(h.run('cloudEvidencePreview'),null,'outdated file reappeared as a valid preview');
  assert.equal(h.context.$('cloud-evidence-preview').hidden,true);
});

test('changing publication target while reading a file cannot mix target and envelope',async()=>{
  const file=deferred(),h=harness();
  h.context.$('cloud-publish-device').value='edge-a';h.context.$('cloud-publish-sequence').value='1';
  h.context.$('cloud-policy').files=[{size:20,text:()=>file.promise}];
  const job=h.forms.get('cloud-publish-form')();
  h.context.$('cloud-publish-device').value='edge-b';h.event('cloud-publish-device','input');
  file.resolve('{"payload":{"device_id":"edge-a"}}');await job;
  assert.equal(h.context.calls.length,0,'preview mixed a previous file with edited publication fields');
  assert.equal(h.run('cloudPublicationPreview'),null);
});

test('an unchanged file and operator session can create an actionable preview',async()=>{
  const h=harness();h.context.$('cloud-evidence').files=[{size:5,text:async()=>'{"v":1}'}];
  await h.forms.get('cloud-evidence-form')();
  assert.equal(h.context.calls.length,1);
  assert.equal(h.run('cloudEvidencePreview.verified.v'),1);
  assert.equal(h.context.$('cloud-evidence-preview').hidden,false);
  assert.equal(h.context.$('cloud-evidence-commit').disabled,false);
});

test('locking invalidates pending evidence and publication confirmations',async()=>{
  const h=harness();
  h.run('cloudEvidencePreview={verified:{},preview:{},epoch:1};cloudPublicationPreview={body:{},preview:{},epoch:1};');
  h.docEvents.get('ops:locked')();
  assert.equal(h.run('cloudEvidencePreview'),null);
  assert.equal(h.run('cloudPublicationPreview'),null);
  assert.equal(h.context.$('cloud-evidence-commit').disabled,true);
  assert.equal(h.context.$('cloud-publish-commit').disabled,true);
});

test('navigation invalidates an otherwise actionable preview',async()=>{
  const h=harness();h.context.$('cloud-evidence').files=[{size:5,text:async()=>'{"v":1}'}];
  await h.forms.get('cloud-evidence-form')();
  assert.notEqual(h.run('cloudEvidencePreview'),null);
  const listener=h.docEvents.get('ops:view');
  assert.equal(typeof listener,'function','upload previews have no navigation invalidation');
  listener({detail:{view:'deployment'}});
  assert.equal(h.run('cloudEvidencePreview'),null);
  assert.equal(h.context.$('cloud-evidence-commit').disabled,true);
});
