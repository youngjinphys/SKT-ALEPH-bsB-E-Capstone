import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

// Execute the real shared controller, including the HTTP/auth boundary. Only
// DOM/network transport is synthetic; no production credentials or API calls.
const raw=readFileSync(new URL('../../apps/policy-server/src/policy_server/console_script.py',import.meta.url),'utf8');
const source=raw.split('JS = r"""')[1].split('\n"""')[0].split('$("login-form").addEventListener')[0];
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const response=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
const publication=(device='edge-a',sequence=12)=>({device,state:'SIGNED_FILE_VERIFIED',sequence,policy_sha256:'hash-'+sequence,
  active_blocks:1,expires_at:'2030-01-01T00:00:00Z',key_id:'policy-key',rules:[{domain:device+'.example',decision:'BLOCK',expires_at:'2030-01-01T00:00:00Z'}]});
const nodes=()=>[{device_id:'edge-a',label:'First node',dns_address:'192.0.2.1',key_id:'node-key',state:'LOCAL_DNS_VERIFIED',
  received_at:'2026-11-04T02:00:00Z',published_sequence:12,published_sha256:'hash-12',dns_applied:true}];
class Element {
  constructor(tag='div'){this.tagName=tag;this.textContent='';this.value='';this.hidden=false;this.disabled=false;this.children=[];this.dataset={};this.attrs={};this.listeners={};this.classList={add(){},remove(){},toggle(){}};}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];this.textContent='';}
  setAttribute(k,v){this.attrs[k]=v;}
  removeAttribute(k){delete this.attrs[k];}
  addEventListener(k,fn){this.listeners[k]=fn;}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(selector==='button'&&child.tagName==='button'?[child]:[]),...child.querySelectorAll(selector)]);}
  reset(){}
}
function harness(){
  const elements=new Map(),events=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  let responder=path=>response(path.includes('/deployment')?publication():nodes());
  const ctx=vm.createContext({console,Date,Map,Set,Response,AbortController,setTimeout,clearTimeout,Event,
    document:{getElementById:get,createElement:tag=>new Element(tag),querySelector:get,querySelectorAll:()=>[],body:new Element(),
      dispatchEvent:event=>{for(const fn of events.get(event.type)||[])fn(event);},addEventListener:(name,fn)=>{events.set(name,[...(events.get(name)||[]),fn]);}},
    Option:function(text,value){const e=new Element('option');e.textContent=text;e.value=value;return e;},
    fetch:(path,opts)=>responder(path,opts),cancelConfirmation(){},confirmOperation:async()=>true,renderAttention(){},expireIdleSession:()=>false,
    loadAnalytics:async()=>{},loadCapabilities(){},opsCapabilities:null,lastNodeItems:[]});
  vm.runInContext(source,ctx);
  const run=code=>vm.runInContext(code,ctx);
  run("token='session-a';sessionEpoch=1;currentView='deployment';");
  get('node-state-filter').value='all';
  return {ctx,run,get,setResponder:fn=>{responder=fn;},seed:()=>run('loadDeployment()')};
}

test('same-target refresh preserves rows and values until completion; identical data keeps DOM identity',async()=>{
  const h=harness();await h.seed();
  const node=h.get('nodes-list').children[0],rule=h.get('published-list').children[0],pending=deferred();
  h.setResponder(async path=>{await pending.promise;return response(path.includes('/deployment')?publication():nodes());});
  const job=h.run('loadDeployment()');
  assert.equal(h.get('nodes-list').children[0],node);
  assert.equal(h.get('published-list').children[0],rule);
  assert.equal(h.get('deployment-sequence').textContent,'12');
  assert.match(h.get('deployment-observed').textContent,/갱신 중.*마지막 조회/);
  assert.equal(h.get('[data-panel="deployment"]').attrs['aria-busy'],'true');
  assert.ok(h.get('nodes-list').querySelectorAll('button').every(x=>x.disabled));
  pending.resolve();await job;
  assert.equal(h.get('nodes-list').children[0],node);
  assert.equal(h.get('published-list').children[0],rule);
  assert.ok(h.get('nodes-list').querySelectorAll('button').every(x=>!x.disabled));
  assert.equal(h.get('[data-panel="deployment"]').attrs['aria-busy'],undefined);
});

test('filter edits made during refresh apply after the same payload completes',async()=>{
  const h=harness();await h.seed();const pending=deferred();
  h.setResponder(async path=>{await pending.promise;return response(path.includes('/deployment')?publication():nodes());});
  const job=h.run('loadDeployment()');h.get('node-search').value='does-not-match';pending.resolve();await job;
  assert.equal(h.get('node-visible-count').textContent,'0 / 1개');
});

test('filter changed before refresh then reverted while pending uses actual rendered filter',async()=>{
  const h=harness();await h.seed();
  h.get('node-state-filter').value='attention';h.run('renderNodes(lastNodeItems)');
  assert.equal(h.get('node-visible-count').textContent,'0 / 1개');
  const pending=deferred();h.setResponder(async path=>{await pending.promise;return response(path.includes('/deployment')?publication():nodes());});
  const job=h.run('loadDeployment()');h.get('node-state-filter').value='all';h.run('renderNodes(lastNodeItems)');
  pending.resolve();await job;assert.equal(h.get('node-visible-count').textContent,'1 / 1개');
  assert.equal(h.get('nodes-list').children[0].className,'node-card');
});

for(const failed of ['nodes','publication'])test(`${failed} outage clears only failed evidence and identical recovery repaints`,async()=>{
  const h=harness();await h.seed();
  h.setResponder(path=>response((failed==='nodes'?path.endsWith('/nodes'):path.includes('/deployment'))?{error:'outage'}:path.includes('/deployment')?publication():nodes(),
    (failed==='nodes'?path.endsWith('/nodes'):path.includes('/deployment'))?503:200));
  const result=await h.run('loadDeployment()');assert.equal(result.partial,true);
  if(failed==='nodes'){
    assert.equal(h.get('deployment-sequence').textContent,'12');assert.equal(h.run('nodesReadValid'),false);
    assert.equal(h.get('edge-read-node').textContent,'–');assert.equal(h.get('nodes-list').children[0].className,'empty-list');
  }else{
    assert.equal(h.get('deployment-sequence').textContent,'–');assert.equal(h.run('publishedRules.length'),0);
    assert.equal(h.get('published-count').textContent,'–');assert.equal(h.get('nodes-list').children[0].className,'node-card');
  }
  h.setResponder(path=>response(path.includes('/deployment')?publication():nodes()));await h.run('loadDeployment()');
  assert.equal(h.get('deployment-sequence').textContent,'12');assert.equal(h.get('published-list').children[0].className,'published-row');
  assert.equal(h.get('nodes-list').children[0].className,'node-card');
});

test('target change clears old publication immediately and ignores late old-target replies',async()=>{
  const h=harness();await h.seed();const slow=deferred();
  h.setResponder(async path=>{if(path.endsWith('/deployment/edge-a'))await slow.promise;return response(path.includes('/deployment')?publication(path.endsWith('edge-b')?'edge-b':'edge-a',path.endsWith('edge-b')?5:12):nodes());});
  const old=h.run('loadDeployment()');h.run("selectedDeploymentDevice='edge-b'");const next=h.run('loadDeployment()');
  assert.equal(h.get('deployment-sequence').textContent,'–');assert.equal(h.run('publishedRules.length'),0);
  await next;slow.resolve();await old;
  assert.equal(h.get('deployment-device').textContent,'edge-b');assert.equal(h.get('deployment-sequence').textContent,'5');
});

test('A to pending B to A reconstructs rows cleared for the different target',async()=>{
  const h=harness();await h.seed();const slow=deferred();
  h.setResponder(async path=>{if(path.endsWith('/deployment/edge-b')){await slow.promise;return response(publication('edge-b',5));}return response(path.includes('/deployment')?publication():nodes());});
  h.run("selectedDeploymentDevice='edge-b'");const old=h.run('loadDeployment()');
  h.run("selectedDeploymentDevice='edge-a'");await h.run('loadDeployment()');
  assert.equal(h.get('published-list').children[0].className,'published-row');
  assert.equal(h.get('nodes-list').children[0].className,'node-card');
  slow.resolve();await old;assert.equal(h.get('deployment-device').textContent,'edge-a');
});

test('newer same-target response wins over a delayed manual/automatic request',async()=>{
  const h=harness();await h.seed();const slow=deferred();let first=true;
  h.setResponder(async path=>{if(path.includes('/deployment')){if(first){first=false;await slow.promise;return response(publication());}return response(publication('edge-a',13));}return response(nodes());});
  const old=h.run('loadDeployment()');await h.run('loadDeployment()');slow.resolve();await old;
  assert.equal(h.get('deployment-sequence').textContent,'13');
});

test('logout purges cached and scalar observations and ignores in-flight data after reauthentication',async()=>{
  const h=harness();await h.seed();const slow=deferred();h.get('stat-candidates').textContent='private-count';h.get('audit-list').append(new Element());
  h.setResponder(async path=>{await slow.promise;return response(path.includes('/deployment')?publication():nodes());});
  const job=h.run('loadDeployment()');h.run('lock()');
  assert.equal(h.run('deploymentSnapshot'),null);assert.equal(h.get('deployment-sequence').textContent,'–');
  assert.equal(h.get('stat-candidates').textContent,'–');assert.equal(h.get('audit-list').children.length,0);
  h.run("token='session-b';sessionEpoch++");slow.resolve();await job;
  assert.equal(h.get('nodes-list').children.length,0);assert.equal(h.run('deploymentSnapshot'),null);
});

test('idle expiry during refresh clears protected observations before a late response',async()=>{
  const h=harness();await h.seed();const slow=deferred();
  h.setResponder(async path=>{await slow.promise;return response(path.includes('/deployment')?publication():nodes());});
  const job=h.run('loadDeployment()');
  const idle=raw.slice(raw.indexOf('function expireIdleSession()'),raw.indexOf('window.setInterval(()=>',raw.indexOf('function expireIdleSession()')));
  h.run(idle);h.run('lastActivity=Date.now()-SESSION_IDLE_MS;expireIdleSession();clearTimeout(toastTimer)');
  assert.equal(h.run('token'),null);assert.equal(h.get('deployment-sequence').textContent,'–');
  slow.resolve();await job;assert.equal(h.get('nodes-list').children.length,0);
});

for(const status of [401,403])for(const body of ['{}','not-json'])test(`${status} ${body==='{}'?'JSON':'non-JSON'} purges authenticated observations before parsing`,async()=>{
  const h=harness();await h.seed();h.setResponder(()=>new Response(body,{status}));
  await h.run('loadDeployment()');
  assert.equal(h.run('token'),null);assert.equal(h.run('deploymentSnapshot'),null);
  assert.equal(h.get('deployment-sequence').textContent,'–');assert.equal(h.get('nodes-list').children.length,0);
});

test('an old forbidden response cannot lock a newer session',async()=>{
  const h=harness();await h.seed();const slow=deferred();h.setResponder(async()=>{await slow.promise;return new Response('forbidden',{status:403});});
  const job=h.run('loadDeployment()');h.run("lock();token='session-b';sessionEpoch++");slow.resolve();await job;
  assert.equal(h.run('token'),'session-b');
});

test('overview failure does not finish its poll until the concurrent analytics read settles',async()=>{
  const h=harness();const analytics=deferred();h.ctx.loadAnalytics=()=>analytics.promise;h.setResponder(()=>response({error:'outage'},503));
  h.run("currentView='overview'");let settled=false;
  const job=h.run('refreshView("overview")').catch(()=>{settled=true;});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(settled,false);
  analytics.resolve();await job;assert.equal(settled,true);
});
