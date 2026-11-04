import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const pinSource=readFileSync(new URL('../../cloud/pin_actions.js',import.meta.url),'utf8');
const actionsSource=readFileSync(new URL('../../cloud/actions.js',import.meta.url),'utf8')
  .replace(/\ncloudConnect\(\);\s*$/,'\n');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const ok=(value={})=>({ok:true,status:200,json:async()=>value});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(fetcher=async()=>ok(),operator=async()=>({email:'test-pin-operator'})){
  const elements=new Map(),events=new Map();
  const context=vm.createContext({console,fetchCalls:[],apiCalls:[],messages:{},redirects:[],unlocked:false,
    fetch:(path,options)=>{context.fetchCalls.push({path,options});return fetcher(path,options);},
    api:async path=>{context.apiCalls.push(path);return operator(path);},
    $:id=>{if(!elements.has(id))elements.set(id,{value:'',hidden:false,disabled:false,required:false,
      attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
      addEventListener:(kind,fn)=>events.set(`${id}:${kind}`,fn)});return elements.get(id);},
    document:{querySelector:()=>context.$('google'),addEventListener(){}},
    showText:(id,text)=>context.messages[id]=text,bindAsyncForm(){},displayError(){},toast(){},
    loadReviews(){},loadDeployment(){},window:{location:{assign:path=>context.redirects.push(path)}}});
  vm.runInContext(`let token=null;let sessionEpoch=0;
    function lock(){sessionEpoch++;token=null;unlocked=false;}
    function unlock(){sessionEpoch++;unlocked=true;}`,context);
  vm.runInContext(pinSource+'\n'+actionsSource,context);
  return {context,events,run:source=>vm.runInContext(source,context),
    submit:()=>events.get('cloud-pin-form:submit')({preventDefault(){}}),
    logout:()=>events.get('cloud-logout:click')()};
}

test('PIN submission clears secrets, rejects duplicate submits, and checks operator before unlock',async()=>{
  const pending=deferred(),identity=deferred();
  const h=harness(()=>pending.promise,()=>identity.promise);
  h.context.$('cloud-pin').value='94271538';h.context.$('cloud-access-code').value='synthetic';
  const job=h.submit();
  assert.equal(h.context.$('cloud-pin').value,'');
  assert.equal(h.context.$('cloud-access-code').value,'');
  assert.equal(h.context.$('cloud-pin-submit').disabled,true);
  await h.submit();assert.equal(h.context.fetchCalls.length,1);
  pending.resolve(ok());await tick();
  assert.equal(h.context.unlocked,false);assert.equal(h.context.apiCalls.length,1);
  identity.resolve({email:'test-pin-operator'});await job;
  assert.equal(h.context.unlocked,true);assert.equal(h.context.$('cloud-pin-submit').disabled,false);
});

test('locking during PIN HTTP response prevents stale unlock and operator request',async()=>{
  const pending=deferred(),h=harness(()=>pending.promise);
  const job=h.submit();h.run('lock()');pending.resolve(ok());await job;
  assert.equal(h.context.unlocked,false);assert.equal(h.context.apiCalls.length,0);
});

test('locking while operator check is pending prevents PIN unlock',async()=>{
  const identity=deferred(),h=harness(async()=>ok(),()=>identity.promise);
  const job=h.submit();await tick();h.run('lock()');
  identity.resolve({email:'test-pin-operator'});await job;
  assert.equal(h.context.unlocked,false);
});

test('stale rejected PIN response cannot lock a newer session or change its message',async()=>{
  const pending=deferred(),h=harness(()=>pending.promise);
  const job=h.submit();h.run('lock();unlock()');
  h.context.messages['cloud-pin-message']='new session';
  pending.resolve({ok:false,json:async()=>({error:'old error'})});await job;
  assert.equal(h.context.unlocked,true);assert.equal(h.context.messages['cloud-pin-message'],'new session');
});

test('logout waits for pending PIN cookie response before revocation and never unlocks',async()=>{
  const login=deferred();
  const h=harness((path,options)=>JSON.parse(options.body).action==='login'?login.promise:Promise.resolve(ok()));
  const entering=h.submit(),leaving=h.logout();
  assert.equal(h.context.unlocked,false);assert.equal(h.context.fetchCalls.length,1);
  await h.submit();assert.equal(h.context.fetchCalls.length,1,'submit must be blocked during logout');
  login.resolve(ok());await Promise.all([entering,leaving]);
  assert.equal(h.context.apiCalls.length,0);assert.equal(h.context.unlocked,false);
  assert.deepEqual(h.context.fetchCalls.map(c=>[c.path,JSON.parse(c.options.body).action]),[
    ['/api/ops/test-auth','login'],['/api/ops/test-auth','logout'],['/api/auth','logout']]);
  assert.deepEqual(h.context.redirects,['/']);
});

test('failed PIN revocation leaves UI locked without claiming logout or redirecting',async()=>{
  const h=harness(async()=>({ok:false,status:503}));h.run('unlock()');await h.logout();
  assert.equal(h.context.unlocked,false);assert.equal(h.context.redirects.length,0);
  assert.equal(h.context.fetchCalls.length,1);assert.match(h.context.messages['cloud-login-message'],/확인할 수 없습니다/);
});

test('stale status JSON cannot expose PIN form or report authenticated',async()=>{
  const body=deferred(),h=harness(async()=>({ok:true,json:()=>body.promise}));
  h.context.$('cloud-pin-form').hidden=true;
  const job=h.run('cloudPinStatus(()=>sessionEpoch===0)');await tick();h.run('lock()');
  body.resolve({enabled:true,authenticated:true,additionalCodeRequired:true});
  assert.equal(await job,false);assert.equal(h.context.$('cloud-pin-form').hidden,true);
});

test('logout during pending PIN operator check waits, revokes, and ignores stale identity',async()=>{
  const identity=deferred(),h=harness(async()=>ok(),()=>identity.promise);
  const entering=h.submit();await tick();const leaving=h.logout();
  assert.equal(h.context.fetchCalls.length,1);
  identity.resolve({email:'test-pin-operator'});await Promise.all([entering,leaving]);
  assert.equal(h.context.unlocked,false);assert.deepEqual(h.context.redirects,['/']);
});
