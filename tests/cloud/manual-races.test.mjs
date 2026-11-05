import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const raw=readFileSync(new URL('../../apps/policy-server/src/policy_server/console_manual.py',import.meta.url),'utf8');
const source=raw.split("JS=r'''")[1].split("\n'''")[0];
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
  const els=new Map(),events=new Map(),calls=[],confirms=[],notices=[];let refreshes=0;
  const get=id=>{if(!els.has(id))els.set(id,{value:'',checked:false,hidden:false,children:[],listeners:{},
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);},
    dispatch(name){for(const fn of this.listeners[name]||[])fn({preventDefault(){}});},
    replaceChildren(...c){this.children=c;},reset(){for(const id of ['manual-domain','manual-reviewer','manual-reason','manual-expires'])get(id).value='';get('manual-ack').checked=false;}});return els.get(id);};
  let responder=async(path,request)=>path.endsWith('/preview')?request:{domain:request.domain};
  let confirmation=async facts=>{confirms.push(facts);return true;};
  const ctx=vm.createContext({Date,console,document:{addEventListener(name,fn){(events.get(name)||events.set(name,[]).get(name)).push(fn);}},
    $:get,token:'same-cookie',sessionEpoch:1,viewEpoch:1,currentView:'drafts',
    staleRequest(){return Object.assign(Error('stale'),{stale:true});},
    api:(path,request)=>{calls.push({path,request});return responder(path,request);},
    confirmOperation:x=>confirmation(x),bindAsyncForm:(id,fn)=>get(id).addEventListener('submit',fn),
    toast(message){notices.push(message);},displayError(e){if(!e.stale)throw e;},loadDrafts:async()=>{refreshes++;},showText(){},fmt:x=>x,node(){},pill(){},empty(){}});
  vm.runInContext(source,ctx);
  vm.runInContext("manualData={revision:'rev1',entries:[]}",ctx);
  get('manual-domain').value='example.net';get('manual-reviewer').value='Operator';get('manual-reason').value='Verified reason with enough detail';get('manual-expires').value='2030-01-01T12:00';get('manual-ack').checked=true;
  return {ctx,get,calls,confirms,notices,get refreshes(){return refreshes;},run:s=>vm.runInContext(s,ctx),setResponder:fn=>responder=fn,setConfirmation:fn=>confirmation=fn,
    submit:()=>get('manual-form').listeners.submit[0]({preventDefault(){}})};
}
for(const change of ['view','input'])test(`pending preview is discarded after ${change} change`,async()=>{
  const h=harness(),pending=deferred();h.setResponder(async(path,req)=>{if(path.endsWith('/preview')){await pending.promise;return req;}return {domain:req.domain};});
  const job=h.submit();
  if(change==='view')h.run("currentView='overview';viewEpoch++");
  else {h.get('manual-domain').value='new.example';h.get('manual-domain').dispatch('input');}
  pending.resolve();await job;
  assert.equal(h.confirms.length,0);assert.equal(h.calls.filter(c=>c.path.endsWith('/save')).length,0);
});
for(const change of ['view','session','input'])test(`pending confirmation cannot save after ${change} change`,async()=>{
  const h=harness(),pending=deferred();h.setConfirmation(()=>pending.promise);
  const job=h.submit();await tick();
  if(change==='view')h.run("currentView='overview';viewEpoch++");
  if(change==='session')h.run('sessionEpoch++');
  if(change==='input'){h.get('manual-reason').value='different';h.get('manual-reason').dispatch('input');}
  pending.resolve(true);await job;assert.equal(h.calls.filter(c=>c.path.endsWith('/save')).length,0);
});
test('unchanged preview and confirmation saves once',async()=>{
  const h=harness();await h.submit();assert.equal(h.confirms.length,1);assert.equal(h.calls.filter(c=>c.path.endsWith('/save')).length,1);
});
test('editing while save is pending preserves new form values',async()=>{
  const h=harness(),pending=deferred();h.setResponder(async(path,req)=>{if(path.endsWith('/save'))await pending.promise;return req;});
  const job=h.submit();await tick();h.get('manual-domain').value='new.example';h.get('manual-domain').dispatch('input');
  pending.resolve();await job;assert.equal(h.get('manual-domain').value,'new.example');assert.equal(h.notices.length,1);assert.equal(h.refreshes,1);
});
for(const change of ['view','session'])test(`pending removal confirmation cannot write after ${change} change`,async()=>{
  const h=harness(),pending=deferred();h.setConfirmation(()=>pending.promise);
  const job=h.run("removeManual({domain:'example.net'})").catch(e=>{if(!e.stale)throw e;});await tick();
  if(change==='view')h.run("currentView='overview';viewEpoch++");else h.run('sessionEpoch++');
  pending.resolve(true);await job;assert.equal(h.calls.filter(c=>c.path.endsWith('/remove')).length,0);
});
for(const operation of ['save','remove'])for(const change of ['view','session'])test(`${operation} completed after ${change} change does not alter the new state`,async()=>{
  const h=harness(),pending=deferred();h.setResponder(async(path,req)=>{if(path.endsWith('/'+operation))await pending.promise;return req;});
  const job=operation==='save'?h.submit():h.run("removeManual({domain:'example.net'})").catch(e=>{if(!e.stale)throw e;});
  await tick();if(change==='view')h.run("currentView='overview';viewEpoch++");else h.run('sessionEpoch++');pending.resolve();await job;
  assert.equal(h.notices.length,0);assert.equal(h.refreshes,0);
});
test('successful removal refreshes even if the list was reloaded during the request',async()=>{
  const h=harness(),pending=deferred();h.setResponder(async(path,req)=>{await pending.promise;return req;});
  const job=h.run("removeManual({domain:'example.net'})");await tick();h.run("manualData={revision:'rev2',entries:[]}");
  pending.resolve();await job;assert.equal(h.notices.length,1);assert.equal(h.refreshes,1);
});
