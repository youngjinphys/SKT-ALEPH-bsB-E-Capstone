import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source=readFileSync(new URL('../../cloud/tutorial.py',import.meta.url),'utf8').match(/JS = r'''([\s\S]*?)'''/)[1];
function harness(connected=true){
  const elements=new Map(),listeners=new Map();
  let modal=false;
  const classes=()=>{const values=new Set();return {add:x=>values.add(x),remove:x=>values.delete(x),contains:x=>values.has(x)};};
  const document={activeElement:null,body:{classList:classes()},
    addEventListener:(type,fn)=>{if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(fn);},
    createElement:()=>element(),getElementById:id=>get(id),
    querySelectorAll:selector=>selector==='[data-cloud-guide-target]'?[...elements.values()].filter(e=>e.attrs.has('data-cloud-guide-target')):[],
    querySelector:selector=>selector==='dialog[open]'?(modal?{}:null):selector==='a.brand'?get('brand'):get(selector)};
  function element(id=''){
    return {id,attrs:new Map(),events:new Map(),hidden:false,disabled:false,textContent:'',children:[],isConnected:true,scrollTop:99,
      setAttribute(k,v){this.attrs.set(k,v);},removeAttribute(k){this.attrs.delete(k);},
      addEventListener(k,f){this.events.set(k,f);},append(e){this.children.push(e);},replaceChildren(){this.children=[];},
      focus(){document.activeElement=this;},closest(){return this.hidden?this:null;},
      querySelector:selector=>get(selector),click(){if(!this.disabled)this.events.get('click')?.({});}};
  }
  function get(id){if(!elements.has(id))elements.set(id,element(id));return elements.get(id);}
  get('authorized').hidden=!connected;get('cloud-guide').hidden=true;
  const context=vm.createContext({document,currentView:'overview',navigateTo:view=>{context.navigations.push(view);context.currentView=view;get('page-title').focus();},navigations:[]});
  vm.runInContext(source,context);
  return {get,context,document,open(){get('cloud-guide-open').focus();get('cloud-guide-open').click();},
    emit:(type,event={})=>listeners.get(type)?.forEach(fn=>fn(event)),setModal:v=>modal=v,
    setConnected:value=>{get('authorized').hidden=!value;},
    next(n=1){for(let i=0;i<n;i++)get('cloud-guide-next').click();}};
}

test('opens only on request, focuses its heading and restores launcher on close',()=>{
  const h=harness();assert.equal(h.get('cloud-guide').hidden,true);
  h.open();assert.equal(h.get('cloud-guide').hidden,false);assert.equal(h.document.activeElement.id,'cloud-guide-title');
  assert.equal(h.get('cloud-guide-open').attrs.get('aria-expanded'),'true');
  assert.equal(h.get('brand').attrs.has('data-cloud-guide-target'),true);
  h.get('cloud-guide-close').click();assert.equal(h.get('cloud-guide').hidden,true);
  assert.equal(h.document.activeElement.id,'cloud-guide-open');assert.equal(h.get('brand').attrs.has('data-cloud-guide-target'),false);
  assert.equal(h.context.navigations.length,0);
});
test('all seven steps are read-only; previous/next are bounded and completion resets',()=>{
  const h=harness();h.open();assert.equal(h.get('cloud-guide-prev').disabled,true);
  const sections=[];
  for(let i=0;i<7;i++){
    sections.push(h.get('cloud-guide-section').textContent);
    assert.equal(h.get('cloud-guide-count').textContent,`0${i+1} / 07`);
    assert.equal(h.get('cloud-guide-instructions').children.length,3);
    assert.equal(h.get('cloud-guide-progress').value,i+1);
    h.next();
  }
  assert.deepEqual(sections,['시작하기','운영 개요','위협 검토','위험도 제안','DNS 정책 초안','배포 현황','작업 기록']);
  assert.equal(h.context.navigations.length,0);assert.equal(h.get('cloud-guide').hidden,true);
  h.open();assert.equal(h.get('cloud-guide-count').textContent,'01 / 07');
});
test('dismiss and reopen preserves the current step; previous returns one step',()=>{
  const h=harness();h.open();h.next(3);h.get('cloud-guide-close').click();h.open();
  assert.equal(h.get('cloud-guide-section').textContent,'위험도 제안');
  h.get('cloud-guide-prev').click();assert.equal(h.get('cloud-guide-section').textContent,'위협 검토');
});
test('only explicit view button navigates; HUD closes and focus moves to page heading',()=>{
  const h=harness();h.open();h.next(2);
  assert.equal(h.context.navigations.length,0);h.get('cloud-guide-view').click();
  assert.deepEqual(h.context.navigations,['reviews']);assert.equal(h.get('cloud-guide').hidden,true);
  assert.equal(h.document.activeElement.id,'page-title');assert.equal(h.document.body.classList.contains('cloud-guide-visible'),false);
});
test('opening the already selected screen does not refetch or reset the current form',()=>{
  const h=harness();h.open();h.next();h.get('cloud-guide-view').click();
  assert.equal(h.context.navigations.length,0);assert.equal(h.document.activeElement.id,'page-title');
});
test('unauthenticated users can read the guide but cannot navigate or authenticate',()=>{
  const h=harness(false);h.open();assert.match(h.get('cloud-guide-description').textContent,/Google/);
  assert.equal(h.get('login-view').attrs.has('data-cloud-guide-target'),true);
  h.next(5);assert.equal(h.get('cloud-guide-view').disabled,true);h.get('cloud-guide-view').click();
  assert.equal(h.context.navigations.length,0);assert.equal(h.get('cloud-guide').hidden,false);
});
test('session locking dismisses guide, clears target and resets progress',()=>{
  const h=harness();h.open();h.next(4);h.emit('ops:locked');h.setConnected(false);
  assert.equal(h.get('cloud-guide').hidden,true);assert.equal(h.document.querySelectorAll('[data-cloud-guide-target]').length,0);
  h.open();assert.equal(h.get('cloud-guide-count').textContent,'01 / 07');assert.match(h.get('cloud-guide-description').textContent,/Google/);
});
test('Escape closes guide without overriding an active operations confirmation dialog',()=>{
  const h=harness();h.open();let prevented=0;const key={key:'Escape',preventDefault:()=>prevented++};
  h.setModal(true);h.emit('keydown',key);assert.equal(h.get('cloud-guide').hidden,false);assert.equal(prevented,0);
  h.setModal(false);h.emit('keydown',key);assert.equal(h.get('cloud-guide').hidden,true);assert.equal(prevented,1);
});
test('repeated open events never duplicate steps or shift focus unexpectedly',()=>{
  const h=harness();h.open();h.get('cloud-guide-open').click();
  assert.equal(h.get('cloud-guide-instructions').children.length,3);
  h.get('page-title').focus();h.emit('ops:view');assert.equal(h.document.activeElement.id,'page-title');
});
