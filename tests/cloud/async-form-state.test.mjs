import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source=readFileSync(new URL('../../apps/policy-server/src/policy_server/console_workbench.py',import.meta.url),'utf8');
const fn=source.slice(source.indexOf('function bindAsyncForm('),source.indexOf('\nasync function loadCapabilities()',source.indexOf('function bindAsyncForm(')));

function harness(handler){
  const attrs=new Map();
  const button={disabled:false,getAttribute:key=>attrs.has(key)?attrs.get(key):null,setAttribute:(key,value)=>attrs.set(key,value),removeAttribute:key=>attrs.delete(key)};
  let onSubmit;
  const form={dataset:{},querySelectorAll:()=>[button],addEventListener:(event,fn)=>{assert.equal(event,'submit');onSubmit=fn;}};
  const context=vm.createContext({document:{getElementById:()=>form},handler});
  vm.runInContext(fn+'\nbindAsyncForm("form",handler);',context);
  return {button,attrs,form,submit:()=>onSubmit({preventDefault(){}})};
}

test('submit completion preserves a newer disabled state and prevents duplicate work',async()=>{
  let release,started=0;
  const waiting=new Promise(resolve=>{release=resolve;});
  const h=harness(async()=>{started++;await waiting;h.button.disabled=true;});
  const first=h.submit();
  assert.equal(h.attrs.get('aria-busy'),'true');
  assert.equal(h.attrs.get('aria-disabled'),'true');
  await h.submit();
  assert.equal(started,1);
  release();await first;
  assert.equal(h.button.disabled,true,'latest validation must keep the submit button disabled');
  assert.equal(h.attrs.has('aria-busy'),false);
  assert.equal(h.attrs.has('aria-disabled'),false);
  assert.equal(h.form.dataset.busy,undefined);
});

test('prior accessibility state is restored even when the handler rejects',async()=>{
  const h=harness(async()=>{throw Error('failed');});
  h.button.setAttribute('aria-disabled','false');
  await assert.rejects(h.submit(),/failed/);
  assert.equal(h.attrs.get('aria-disabled'),'false');
  assert.equal(h.attrs.has('aria-busy'),false);
  assert.equal(h.form.dataset.busy,undefined);
});
