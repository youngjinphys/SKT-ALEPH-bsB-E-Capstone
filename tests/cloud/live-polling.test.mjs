import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const path=new URL('../../apps/policy-server/src/policy_server/console_live.py',import.meta.url);
function factory(){assert.ok(fs.existsSync(path),'live polling controller missing');const code=fs.readFileSync(path,'utf8').match(/JS = r'''([\s\S]*?)'''/)[1];const end=code.indexOf('// Browser integration');const ctx=vm.createContext({});vm.runInContext(code.slice(0,end),ctx);return ctx.createLivePoller;}
function harness(task){let eligible=true,id=0;const jobs=new Map(),states=[];const p=factory()({poll:task,eligible:()=>eligible,onState:s=>states.push(s),onError:()=>{},setTimer:(fn,ms)=>{const n=++id;jobs.set(n,{fn,ms});return n;},clearTimer:n=>jobs.delete(n),period:10000});return{p,jobs,states,setEligible:x=>eligible=x,async fire(){const [id,j]=jobs.entries().next().value;jobs.delete(id);await j.fn();}};}
test('one active request; next timer is scheduled only after completion',async()=>{let done,calls=0;const h=harness(()=>{calls++;return new Promise(r=>done=r)});h.p.resume();const run=h.fire();assert.equal(calls,1);assert.equal(h.jobs.size,0);h.p.resume();assert.equal(h.jobs.size,0);done();await run;assert.equal(h.jobs.size,1);assert.equal([...h.jobs.values()][0].ms,10000);});
test('network failures back off, pause removes timers and stale requests cannot restart',async()=>{const h=harness(async()=>{throw Error('offline')});h.p.resume();await h.fire();assert.equal([...h.jobs.values()][0].ms,20000);await h.fire();assert.equal([...h.jobs.values()][0].ms,40000);h.p.stop();assert.equal(h.jobs.size,0);h.setEligible(false);h.p.resume();assert.equal(h.jobs.size,0);});
test('locking while a request is running prevents rescheduling',async()=>{let done;const h=harness(()=>new Promise(r=>done=r));h.p.resume();const run=h.fire();h.p.stop();done();await run;assert.equal(h.jobs.size,0);});

function browserHarness(task){
  const code=fs.readFileSync(path,'utf8').match(/JS = r'''([\s\S]*?)'''/)[1];
  let id=0;const jobs=new Map(),listeners=new Map(),elements=new Map(),messages=[];
  const get=name=>{if(!elements.has(name))elements.set(name,{dataset:{},addEventListener(){},setAttribute(){}});return elements.get(name);};
  const ctx=vm.createContext({navigator:{onLine:true},document:{hidden:false,querySelector:get,addEventListener:(name,fn)=>listeners.set(name,fn)},
    window:{setTimeout:(fn,ms)=>{jobs.set(++id,{fn,ms});return id;},clearTimeout:n=>jobs.delete(n),setInterval(){},addEventListener(){}},
    $:get,showText:(name,text)=>{messages.push({name,text});get(name).textContent=text;},refreshView:task,expireIdleSession:()=>false,obsTick(){}});
  vm.runInContext("let token='test-session',obsPaused=false,currentView='deployment',obsLastFetch=0,sessionEpoch=1,viewEpoch=1,obsRequest=0;const viewRequestEpochs={};function staleRequest(){return Object.assign(Error('STALE_SESSION'),{stale:true});}",ctx);vm.runInContext(code,ctx);
  return {run:code=>vm.runInContext(code,ctx),jobs,listeners,messages,get,async fire(){const [id,j]=jobs.entries().next().value;jobs.delete(id);await j.fn();}};
}
test('partial deployment result is an error and backs off rather than claiming live',async()=>{
  const h=browserHarness(async()=>({partial:true}));h.run('syncOpsLive()');await h.fire();
  assert.equal([...h.jobs.values()][0].ms,20000);
  assert.match(h.get('verification-status').textContent,/조회 실패/);
  assert.equal(h.get('obs-live').dataset.state,'error');
});
test('a pending old-view error cannot overwrite the new view or restart its poll epoch',async()=>{
  let reject;const h=browserHarness(()=>new Promise((_,no)=>{reject=no;}));
  h.run("currentView='overview';syncOpsLive()");const old=h.fire();
  h.run("currentView='deployment'");h.listeners.get('ops:poll-view')();
  h.get('verification-status').textContent='new deployment state';reject(Error('old overview failure'));await old;
  assert.equal(h.get('verification-status').textContent,'new deployment state');
  assert.equal(h.get('obs-live').dataset.state,'live');
  assert.equal([...h.jobs.values()][0].ms,10000);
});

test('superseded automatic failure cannot replace a newer manual success status',async()=>{
  let reject;const h=browserHarness(()=>new Promise((_,no)=>{reject=no;}));h.run('syncOpsLive()');const old=h.fire();
  h.run("viewRequestEpochs.deployment=2");h.get('verification-status').textContent='new successful manual result';
  reject(Error('old failure'));await old;
  assert.equal(h.get('verification-status').textContent,'new successful manual result');
  assert.equal(h.run('opsLive.inspect().failures'),0);
});
test('superseded automatic success cannot hide a newer manual failure',async()=>{
  let resolve;const h=browserHarness(()=>new Promise(yes=>{resolve=yes;}));h.run('syncOpsLive()');const old=h.fire();
  h.run("viewRequestEpochs.deployment=2");h.get('verification-status').textContent='new manual read failed';h.get('obs-live').dataset.state='error';
  resolve({partial:false});await old;
  assert.equal(h.get('verification-status').textContent,'new manual read failed');assert.equal(h.get('obs-live').dataset.state,'error');
});
