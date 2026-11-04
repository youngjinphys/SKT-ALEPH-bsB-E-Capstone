import test from 'node:test';
import assert from 'node:assert/strict';
import {authReturnPath, authFailurePath} from '../../apps/web/src/lib/auth-destination.ts';

test('only the exact dashboard path preserves the operations destination',()=>{
  assert.equal(authReturnPath('/dashboard'),'/dashboard');
  for(const value of [null,undefined,'/app','//evil.test','https://evil.test','/dashboard/../api','/dashboard?x=1','%2Fdashboard'])
    assert.equal(authReturnPath(value),'/app');
});
test('cancelled or disabled dashboard login returns to the same dashboard',()=>{
  assert.equal(authFailurePath('/dashboard','cancelled'),'/dashboard?auth_error=cancelled');
  assert.equal(authFailurePath('/dashboard','google_disabled'),'/dashboard?auth_error=google_disabled');
  assert.equal(authFailurePath('/app','cancelled'),'/?auth_error=cancelled');
});
test('untrusted OAuth error text is never reflected into a redirect',()=>{
  for(const reason of ['<script>x</script>','constructor','__proto__','cancelled&next=https://evil.test'])
    assert.equal(authFailurePath('/dashboard',reason),'/dashboard?auth_error=auth_unavailable');
});
