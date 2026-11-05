import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const shared=readFileSync(new URL('../../apps/policy-server/src/policy_server/console_script.py',import.meta.url),'utf8');
const preview=shared.slice(shared.indexOf('let draftImpactEpoch=0;'),shared.indexOf('async function downloadDraft('));
const buildStart=shared.indexOf('bindAsyncForm("build-form"');
const build=shared.slice(buildStart,shared.indexOf('$("deployment-device-select")',buildStart));
const cloud=readFileSync(new URL('../../cloud/actions.js',import.meta.url),'utf8').replace(/\ncloudConnect\(\);\s*$/,'\n');
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
 const elements=new Map(),events=new Map(),forms=new Map(),notices=[],errors=[],calls=[];let response=async()=>({});let deployment=async()=>{};let drafts=async()=>{};
 const make=(tag='div',className='',value='')=>({tagName:tag,className,textContent:value,value:'',hidden:false,disabled:false,checked:false,files:[],children:[],dataset:{},
  addEventListener(name,fn){(this.listeners??={})[name]=fn;},append(...c){this.children.push(...c);},replaceChildren(...c){this.children=c;},setAttribute(){},removeAttribute(){},reset(){}});
 const get=id=>{if(!elements.has(id))elements.set(id,make());return elements.get(id);};
 const ctx=vm.createContext({console,Date,document:{getElementById:get,querySelector:()=>make(),addEventListener(){},},$:get,node:make,fmt:x=>x,
  bindAsyncForm:(id,fn)=>forms.set(id,fn),api:async(path,body)=>{calls.push({path,body});return response(path,body);},
  toast:(msg,error)=>notices.push({msg,error}),displayError:e=>{if(!e.stale)errors.push(e.message);},
  loadDeployment:()=>deployment(),loadDrafts:()=>drafts(),confirmOperation:async()=>true,
  staleRequest:()=>Object.assign(Error('STALE_SESSION'),{stale:true}),window:{location:{assign(){}}},fetch:async()=>({ok:false,status:401})});
 vm.runInContext(`let token='cookie-session',sessionEpoch=1,viewEpoch=1,currentView='drafts',selectedReview=null;let buildReviewContext={manual_revision:'m',review_set_revision:'r',expired:[]};const viewRequestEpochs=Object.create(null);function currentRequest(name){const view=viewEpoch,session=sessionEpoch,id=(viewRequestEpochs[name]||0)+1;viewRequestEpochs[name]=id;return ()=>!!token&&session===sessionEpoch&&view===viewEpoch&&id===viewRequestEpochs[name]&&currentView===name;}`,ctx);
 vm.runInContext(preview+'\n'+build+'\n'+cloud,ctx);
 const run=code=>vm.runInContext(code,ctx);
 return {ctx,get,run,forms,calls,notices,errors,setResponse:fn=>response=fn,setDeployment:fn=>deployment=fn,setDrafts:fn=>drafts=fn};
}
async function publication(h){h.run("currentView='deployment';cloudPublicationPreview={body:{device_id:'edge-a',expected_sequence:1},preview:{expected_sequence:1,sequence:2,withdrawn_count:0,shortened_count:0},epoch:sessionEpoch,current:cloudOperation(()=>cloudPublicationVersion),committing:false}");}
test('publishing remains visible and preserves changed form after server success',async()=>{
 const h=harness(),pending=deferred();await publication(h);h.setResponse(async()=>{await pending.promise;return {sequence:2};});let refreshes=0;h.setDeployment(async()=>{refreshes++;});
 const job=h.get('cloud-publish-commit').listeners.click();await tick();h.get('cloud-publish-device').value='edge-b';h.get('cloud-publish-device').listeners.input();pending.resolve();await job;
 assert.equal(h.get('cloud-publish-device').value,'edge-b');assert.equal(refreshes,1);assert.match(h.notices.map(x=>x.msg).join(),/게시/);
});
test('successful publication reports result when subsequent status refresh fails',async()=>{
 const h=harness();await publication(h);h.setResponse(async()=>({sequence:2}));h.setDeployment(async()=>{throw Error('offline');});
 await h.get('cloud-publish-commit').listeners.click();assert.match(h.notices.map(x=>x.msg).join(),/게시/);assert.match(h.notices.map(x=>x.msg).join(),/조회/);
});
test('successful draft build reports result when refresh fails',async()=>{
 const h=harness();h.setResponse(async()=>({rules:1,draft:'policy-a.json'}));h.setDrafts(async()=>{throw Error('offline');});
 await h.forms.get('build-form')({preventDefault(){}});assert.match(h.notices.map(x=>x.msg).join(),/생성/);assert.match(h.notices.map(x=>x.msg).join(),/조회/);
});
test('older draft impact cannot overwrite newer selection',async()=>{
 const h=harness(),pending=deferred();h.setResponse(async(path)=>{if(path.includes('old'))await pending.promise;return {comparison_available:false};});
 const old=h.run("previewDraft('old')");await h.run("previewDraft('new')");pending.resolve();await old;
 assert.match(h.get('draft-impact').children[0].textContent,/new/);
});
test('draft impact from an earlier view cannot reappear after leaving and returning',async()=>{
 const h=harness(),pending=deferred();h.setResponse(async()=>{await pending.promise;return {comparison_available:false};});const old=h.run("previewDraft('old')");
 h.run("currentView='overview';viewEpoch++;currentView='drafts';viewEpoch++");pending.resolve();await old;assert.equal(h.get('draft-impact').children.length,0);
});
test('publication warns when status refresh is partial',async()=>{
 const h=harness();await publication(h);h.setResponse(async()=>({sequence:2}));h.setDeployment(async()=>({partial:true}));
 await h.get('cloud-publish-commit').listeners.click();assert.match(h.notices.at(-1).msg,/조회/);assert.equal(h.notices.at(-1).error,true);
});
for(const change of ['view','session'])test(`completed publication does not affect changed ${change}`,async()=>{
 const h=harness(),pending=deferred();await publication(h);h.setResponse(async()=>{await pending.promise;return {sequence:2};});let refreshes=0;h.setDeployment(async()=>{refreshes++;});
 const job=h.get('cloud-publish-commit').listeners.click();await tick();h.run(change==='view'?"currentView='overview';viewEpoch++":"sessionEpoch++");pending.resolve();await job;
 assert.equal(h.notices.length,0);assert.equal(refreshes,0);
});
test('unchanged draft build reports success after successful refresh',async()=>{
 const h=harness();h.setResponse(async()=>({rules:2,draft:'policy-a.json'}));await h.forms.get('build-form')({preventDefault(){}});
 assert.match(h.notices.at(-1).msg,/policy-a.json/);assert.equal(h.errors.length,0);
});
test('stale draft impact error is suppressed after newer selection',async()=>{
 const h=harness(),pending=deferred();h.setResponse(async(path)=>{if(path.includes('old')){await pending.promise;throw Error('old failure');}return {comparison_available:false};});
 const old=h.run("previewDraft('old')").catch(e=>{if(!e.stale)throw e;});await h.run("previewDraft('new')");pending.resolve();await old;assert.match(h.get('draft-impact').children[0].textContent,/new/);
});
