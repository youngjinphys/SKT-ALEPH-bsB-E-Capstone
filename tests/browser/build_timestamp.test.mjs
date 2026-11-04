import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';
import test from 'node:test';

const web = new URL('../../apps/web/', import.meta.url);
const require = createRequire(new URL('package.json', web));
const ts = require('typescript');
const {PHASE_PRODUCTION_BUILD, PHASE_PRODUCTION_SERVER, PHASE_DEVELOPMENT_SERVER} = require('next/constants');
const {renderToStaticMarkup} = require('react-dom/server');

function load(relative, globals = {}) {
  const filename = fileURLToPath(new URL(relative, web));
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const exports = {};
  runInNewContext(source, {exports, require, ...globals}, {filename});
  return exports;
}

test('production build captures the clock once and keeps UTC independent of host timezone', () => {
  let reads = 0;
  const fakeClock = class extends Date {
    constructor() { super('2026-11-04T12:39:00.123+09:00'); reads++; }
  };
  const config = load('next.config.ts', {Date: fakeClock}).default;
  assert.equal(config(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, '2026-11-04T03:39:00.123Z');
  assert.equal(config(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, '2026-11-04T03:39:00.123Z');
  assert.equal(reads, 1);
});

test('development and production-server config never read the clock or invent a new build', () => {
  const forbiddenClock = class { constructor() { throw Error('Runtime clock was read'); } };
  const config = load('next.config.ts', {Date: forbiddenClock}).default;
  for (const phase of [PHASE_PRODUCTION_SERVER, PHASE_DEVELOPMENT_SERVER]) {
    assert.equal(config(phase).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, '');
  }
});

test('a separate build captures its own time instead of a previously generated source file', () => {
  const first = load('next.config.ts', {Date: class extends Date { constructor() { super('2026-11-04T03:39:00Z'); } }}).default;
  const second = load('next.config.ts', {Date: class extends Date { constructor() { super('2026-11-04T04:45:00Z'); } }}).default;
  assert.notEqual(first(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, second(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME);
});

test('watermark uses semantic UTC time with no rendering clock, locale or hydration dependency', () => {
  const forbiddenClock = class { constructor() { throw Error('Rendering clock was read'); } };
  const {BuildTimestamp} = load('src/components/BuildTimestamp.tsx', {
    Date: forbiddenClock, process: {env: {NEXT_PUBLIC_ALEPH_BUILD_TIME: '2026-11-04T03:39:00.123Z'}},
  });
  const html = renderToStaticMarkup(BuildTimestamp());
  assert.match(html, /Updated at <time dateTime="2026-11-04T03:39:00.123Z">2026-11-04 03:39:00 UTC<\/time>/);
});

test('development omits the watermark rather than substituting request time', () => {
  for (const value of [undefined, '']) {
    const {BuildTimestamp} = load('src/components/BuildTimestamp.tsx', {
      process: {env: {NEXT_PUBLIC_ALEPH_BUILD_TIME: value}},
    });
    assert.equal(BuildTimestamp(), null);
  }
});
