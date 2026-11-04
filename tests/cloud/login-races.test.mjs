import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../cloud/actions.js', import.meta.url), 'utf8')
  .replace(/\ncloudConnect\(\);\s*$/, '\n');
function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}
function harness(fetcher, operator = async () => ({ authorized: true, email: 'owner@example.org' })) {
  const elements = new Map();
  const events = new Map();
  const context = vm.createContext({
    fetch: (url, options) => url==='/api/ops/test-auth'?Promise.resolve({ok:true}):fetcher(url,options), console, cloudPinStatus:async()=>false, cloudPinLoginPending:null,
    document: {querySelector: () => context.$('cloud-google-login'),addEventListener() {}},
    $: id => {
      if (!elements.has(id)) elements.set(id, { value: '', files: [], checked: false, attrs: {},
        setAttribute(key,value){this.attrs[key]=value;}, removeAttribute(key){delete this.attrs[key];},
        addEventListener: (kind, callback) => events.set(`${id}:${kind}`, callback) });
      return elements.get(id);
    },
    showText: (id, text) => { context.messages[id] = text; },
    messages: {}, calls: [], unlocked: false, redirects: [],
    window: { location: { assign: path => context.redirects.push(path) } },
    api: async path => { context.calls.push(path); return operator(path); },
    displayError() {}, toast() {}, loadReviews() {}, loadDeployment() {}, bindAsyncForm() {},
  });
  vm.runInContext(`let token=null;let sessionEpoch=0;
    function lock(){sessionEpoch++;token=null;unlocked=false;}
    function unlock(){sessionEpoch++;unlocked=true;}`, context);
  vm.runInContext(source, context);
  return { context, events, elements, run: code => vm.runInContext(code, context) };
}

test('locking during initial authentication cannot be undone by its response', async () => {
  const pending = deferred();
  const h = harness(() => pending.promise);
  const result = h.run('cloudConnect()');
  h.run('lock()');
  pending.resolve({ ok: true, status: 200 });
  await result;
  assert.equal(h.context.unlocked, false);
  assert.equal(h.context.calls.length, 0);
});

test('an obsolete failed login cannot lock a newer authorized session', async () => {
  const pending = deferred(); let count=0;
  const h = harness(() => ++count === 1 ? pending.promise : Promise.resolve({ ok: true, status: 200 }));
  const old = h.run('cloudConnect()'); await new Promise(resolve=>setImmediate(resolve));
  await h.run('cloudConnect()');
  assert.equal(h.context.unlocked, true);
  pending.resolve({ ok: false, status: 401 });
  await old;
  assert.equal(h.context.unlocked, true);
  assert.deepEqual(h.context.calls, ['/api/ops/session']);
});

test('operator authorization is checked before unlocking', async () => {
  const h = harness(async () => ({ ok: true, status: 200 }), async () => {
    throw Error('이 계정에는 DNS 관제 운영자 권한이 없습니다.');
  });
  await h.run('cloudConnect()');
  assert.equal(h.context.unlocked, false);
  assert.match(h.context.messages['cloud-login-message'], /운영자 권한/);
});

test('logout locks immediately and ignores an older in-flight login', async () => {
  const login=deferred(), logout=deferred();
  const h = harness((url, options) => options?.method === 'POST' ? logout.promise : login.promise);
  h.run('unlocked=true');
  const connecting=h.run('cloudConnect()');
  const leaving=h.events.get('cloud-logout:click')();
  assert.equal(h.context.unlocked, false);
  login.resolve({ ok: true, status: 200 }); await connecting;
  assert.equal(h.context.unlocked, false);
  logout.resolve({ ok: true, status: 200 }); await leaving;
  assert.deepEqual(h.context.redirects, ['/']);
});

test('disabled Google provider is shown rather than an unusable sign-in link', async () => {
  const h=harness(async path => path==='/api/auth'
    ? {ok:false,status:401}
    : {ok:true,status:200,json:async()=>({state:'disabled'})});
  await h.run('cloudConnect()');
  assert.equal(h.context.unlocked,false);
  assert.match(h.context.messages['cloud-login-message'],/Google.*비활성/);
  assert.equal(h.elements.get('cloud-google-login').attrs['aria-disabled'],'true');
});


test('provider outage removes a previously enabled Google navigation link', async () => {
  let outage=false;
  const h=harness(async()=>{if(outage)throw Error('network down');return {ok:true,json:async()=>({state:'enabled'})};});
  await h.run('cloudLoginAvailability(()=>true)');
  assert.equal(h.elements.get('cloud-google-login').attrs.href,'/api/oauth?action=start&next=/dashboard');
  outage=true;
  await h.run('cloudLoginAvailability(()=>true)');
  assert.equal(h.elements.get('cloud-google-login').attrs.href,undefined);
  assert.equal(h.elements.get('cloud-google-login').attrs['aria-disabled'],'true');
});
