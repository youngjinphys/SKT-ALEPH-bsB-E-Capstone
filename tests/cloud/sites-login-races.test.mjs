import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../../cloud/sites_actions.js',import.meta.url),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};}
function harness(api){
 const events=new Map(),messages={};
 const ctx=vm.createContext({api,events,messages,unlocked:false,$:id=>({addEventListener:(event,fn)=>events.set(id+':'+event,fn)}),showText:(id,text)=>messages[id]=text});
 vm.runInContext('let token=null;let sessionEpoch=0;function lock(){sessionEpoch++;token=null;unlocked=false;}function unlock(){sessionEpoch++;unlocked=true;}',ctx);
 vm.runInContext(source,ctx);return {ctx,events,messages,run:s=>vm.runInContext(s,ctx)};
}
test('Sites authenticates only through the operator session endpoint',async()=>{
 const h=harness(async path=>{assert.equal(path,'/api/ops/session');return {email:'owner@example.org'};});
 await h.run('cloudConnect()');assert.equal(h.ctx.unlocked,true);
});
test('older Sites authorization cannot unlock after lock or logout',async()=>{
 for(const logout of [false,true]){
  const p=deferred(),h=harness(()=>p.promise),result=h.run('cloudConnect()');
  if(logout)h.events.get('cloud-logout:click')();else h.run('lock()');
  p.resolve({email:'owner@example.org'});await result;assert.equal(h.ctx.unlocked,false);
 }
});
test('older failure cannot lock a newer authorized Sites session',async()=>{
 const p=deferred();let count=0;const h=harness(()=>++count===1?p.promise:Promise.resolve({email:'owner@example.org'}));
 const old=h.run('cloudConnect()');await h.run('cloudConnect()');p.reject(Error('old request failed'));await old;assert.equal(h.ctx.unlocked,true);
});
test('denied operator and upstream outage stay locked with actionable message',async()=>{
 for(const message of ['운영자 권한이 없습니다','관제 서버 연결 실패']){
  const h=harness(async()=>{throw Error(message)});await h.run('cloudConnect()');assert.equal(h.ctx.unlocked,false);assert.equal(h.messages['cloud-login-message'],message);
 }
});
