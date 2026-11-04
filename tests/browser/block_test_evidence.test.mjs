import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const evidencePath = process.env.BLOCK_TEST_EVIDENCE_FILE || new URL('../../apps/web/public/capstone/evidence/block-test-loopback-20261104.json', import.meta.url);
const evidence = JSON.parse(readFileSync(evidencePath, 'utf8'));
const sha = value => createHash('sha256').update(value).digest('hex');
const canonical = value => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
};

test('loopback block.test record binds policy, configuration and raw observations', () => {
  assert.match(evidence.scope, /isolated loopback fixture; not production DNS/);
  assert.match(evidence.source_baseline_commit, /^[a-f0-9]{40}$/);
  assert.equal(evidence.source_execution_mode, 'read-only-permission snapshot');
  assert.deepEqual(evidence.source_hashes_before, evidence.source_hashes_after);
  assert.ok(Object.keys(evidence.source_hashes_before).length >= 2);
  for (const hash of Object.values(evidence.source_hashes_before)) assert.match(hash, /^[a-f0-9]{64}$/);
  assert.ok(Date.parse(evidence.started_at) <= Date.parse(evidence.finished_at));
  assert.match(evidence.upstream_config, /host-record=block\.test,192\.0\.2\.60,2001:db8::60/);
  assert.deepEqual(evidence.phases.map(phase => phase.name), ['before', 'blocked', 'withdrawn']);
  for (const phase of evidence.phases) {
    const blocked = phase.name === 'blocked';
    assert.equal(phase.apply_result.event, 'applied');
    assert.equal(phase.apply_result.blocked_count, Number(blocked));
    assert.equal(phase.apply_result.policy_sha256, sha(canonical(phase.policy)));
    assert.equal(phase.active_config_sha256, sha(phase.active_config));
    assert.equal(phase.active_config.includes('address=/block.test/'), blocked);
    if (blocked) {
      assert.equal(phase.policy.rules.length, 1);
      assert.deepEqual([phase.policy.rules[0].domain, phase.policy.rules[0].decision, phase.policy.rules[0].scope, phase.policy.rules[0].approved], ['block.test', 'BLOCK', 'SUBTREE', true]);
    } else assert.deepEqual(phase.policy.rules, []);
    assert.equal(phase.queries.length, 4);
    assert.equal(new Set(phase.queries.map(q => `${q.qtype}/${q.transport}`)).size, 4);
    for (const q of phase.queries) {
      assert.ok(['A', 'AAAA'].includes(q.qtype));
      assert.ok(['UDP', 'TCP'].includes(q.transport));
      assert.equal(q.exit_code, 0);
      assert.equal(q.rcode, blocked ? 'NXDOMAIN' : 'NOERROR');
      assert.match(q.stdout, new RegExp(`status: ${q.rcode}\\b`));
      assert.equal(q.stdout.includes(q.qtype === 'A' ? '192.0.2.60' : '2001:db8::60'), !blocked);
      assert.ok(q.command.includes('block.test') && q.command.includes(q.qtype));
      assert.equal(q.command.includes('+tcp'), q.transport === 'TCP');
      assert.ok(Date.parse(evidence.started_at) <= Date.parse(q.started_at));
      assert.ok(Date.parse(q.started_at) <= Date.parse(q.finished_at));
      assert.ok(Date.parse(q.finished_at) <= Date.parse(evidence.finished_at));
    }
  }
  assert.equal(evidence.upstream_queries.length, 4);
  assert.equal(new Set(evidence.upstream_queries.map(q => `${q.qtype}/${q.transport}`)).size, 4);
  for (const q of evidence.upstream_queries) {
    assert.equal(q.rcode, 'NOERROR');
    assert.match(q.stdout, /status: NOERROR\b/);
    assert.ok(q.stdout.includes(q.qtype === 'A' ? '192.0.2.60' : '2001:db8::60'));
  }
});
