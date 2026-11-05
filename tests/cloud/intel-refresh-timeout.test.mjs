import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const raw=readFileSync(new URL('../../apps/policy-server/src/policy_server/console_script.py',import.meta.url),'utf8');
const apiSource=raw.slice(raw.indexOf('async function api('),raw.indexOf('\nfunction lock()',raw.indexOf('async function api(')));
const formSource=raw.slice(raw.indexOf('bindAsyncForm("intel-refresh-form"'),raw.indexOf('\n$("intel-import")',raw.indexOf('bindAsyncForm("intel-refresh-form"')));
function harness(fetcher){
  const timers=[],calls=[],forms=new Map(),errors=[],elements=new Map(),messages={};
  const get=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,checked:true,reset(){this.resets=(this.resets||0)+1;}});return elements.get(id);};
  const context=vm.createContext({AbortController,fetch:(path,opts)=>{calls.push({path,opts});return fetcher(path,opts);},
    setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){},
    $:get,expireIdleSession:()=>false,staleRequest:()=>Object.assign(Error('stale'),{stale:true}),
    showText:(id,value)=>{messages[id]=value;},toast(){},bindAsyncForm:(id,fn)=>forms.set(id,fn),displayError:e=>errors.push(e),
    loadIntelStatus:async()=>{},console});
  vm.runInContext("let token='cookie-session',sessionEpoch=1,currentView='reviews';",context);
  vm.runInContext(apiSource,context);vm.runInContext(formSource,context);
  return {context,timers,calls,forms,errors,messages,get,run:code=>vm.runInContext(code,context)};
}
const success=()=>Promise.resolve({ok:true,status:200,json:async()=>({accepted:true,state:'SUCCESS'})});
test('a successful provider response after 25 seconds is accepted',async()=>{
  let finish;
  const h=harness((path,{signal})=>new Promise((resolve,reject)=>{
    finish=()=>resolve({ok:true,status:200,json:async()=>({accepted:true,state:'SUCCESS'})});
    signal.addEventListener('abort',()=>reject(Error('aborted')));
  }));
  const result=h.run("api('/api/ops/intel/refresh',{})");
  for(const timer of h.timers)if(timer.ms<=25000)timer.fn();
  finish();
  assert.equal((await result).state,'SUCCESS');
  assert.ok(h.timers[0].ms>=60000);
});
test('ordinary requests retain their shorter deadline',async()=>{
  const h=harness(success);await h.run("api('/api/ops/overview')");
  assert.equal(h.timers[0].ms,20000);
});
test('lost provider response reports an unknown outcome without resubmitting',async()=>{
  const h=harness(()=>Promise.reject(Error('network')));
  await h.forms.get('intel-refresh-form')({preventDefault(){}});
  assert.equal(h.calls.length,1);
  assert.match(h.errors[0].message,/결과.*확인|결과.*미확정/);
  assert.match(h.errors[0].message,/다시.*조회|상태.*확인/);
  assert.equal(h.get('intel-refresh-form').resets,undefined);
  await Promise.resolve();
  assert.match(h.messages['intel-note'],/결과.*확인/);
});

test('server error after provider submission is also an unknown outcome',async()=>{
  const h=harness(async()=>({ok:false,status:504,json:async()=>({error:'gateway timeout'})}));
  await h.forms.get('intel-refresh-form')({preventDefault(){}});
  assert.equal(h.calls.length,1);
  assert.match(h.errors[0].message,/결과.*확인/);
});
