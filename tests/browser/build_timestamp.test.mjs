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
const {createElement} = require('react');
const INSTANT = '2026-11-04T03:39:00.123Z';

function load(relative, globals = {}) {
  const filename = fileURLToPath(new URL(relative, web));
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const exports = {};
  const resolve = name => name === '@/lib/build-time' ? load('src/lib/build-time.ts', globals) : require(name);
  runInNewContext(source, {exports, require: resolve, ...globals}, {filename});
  return exports;
}

const noCurrentClock = class extends Date {
  constructor(...args) { if (!args.length) throw Error('Current clock was read'); super(...args); }
  static now() { throw Error('Current clock was read'); }
};
const {buildTimeLocal, buildTimeUtc} = load('src/lib/build-time.ts', {Date: noCurrentClock});

test('production build captures the clock once and keeps UTC independent of host timezone', () => {
  let reads = 0;
  const fakeClock = class extends Date {
    constructor() { super('2026-11-04T12:39:00.123+09:00'); reads++; }
  };
  const config = load('next.config.ts', {Date: fakeClock}).default;
  assert.equal(config(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, INSTANT);
  assert.equal(config(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, INSTANT);
  assert.equal(reads, 1);
});

test('development and production-server config never read the clock or invent a new build', () => {
  const config = load('next.config.ts', {Date: noCurrentClock}).default;
  for (const phase of [PHASE_PRODUCTION_SERVER, PHASE_DEVELOPMENT_SERVER]) {
    assert.equal(config(phase).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, '');
  }
});

test('a separate build captures its own time instead of a previously generated source file', () => {
  const first = load('next.config.ts', {Date: class extends Date { constructor() { super('2026-11-04T03:39:00Z'); } }}).default;
  const second = load('next.config.ts', {Date: class extends Date { constructor() { super('2026-11-04T04:45:00Z'); } }}).default;
  assert.notEqual(first(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME, second(PHASE_PRODUCTION_BUILD).env.NEXT_PUBLIC_ALEPH_BUILD_TIME);
});

test('SSR uses accessible UTC fallback without the viewer timezone or current clock', () => {
  const {BuildTimestamp} = load('src/components/BuildTimestamp.tsx', {
    Date: noCurrentClock, Intl: undefined, process: {env: {NEXT_PUBLIC_ALEPH_BUILD_TIME: INSTANT}},
  });
  const html = renderToStaticMarkup(createElement(BuildTimestamp));
  assert.match(html, /dateTime="2026-11-04T03:39:00.123Z"/);
  assert.match(html, /aria-label="웹 빌드 시각: 2026-11-04 03:39:00 UTC"/);
  assert.match(html, /표시 시간대: UTC/);
  assert.match(html, />2026-11-04 03:39:00 UTC<\/time>/);
});

test('missing and malformed metadata never display Invalid Date or substitute current time', () => {
  for (const value of [undefined, '', 'garbage', '2026-02-30T03:39:00.123Z', '2026-11-04T03:39:00', '2026-11-04T03:39:00.123+09:00']) {
    assert.equal(buildTimeUtc(value), null);
    assert.equal(buildTimeLocal(value), null);
    const {BuildTimestamp} = load('src/components/BuildTimestamp.tsx', {
      Date: noCurrentClock, process: {env: {NEXT_PUBLIC_ALEPH_BUILD_TIME: value}},
    });
    assert.equal(renderToStaticMarkup(createElement(BuildTimestamp)), '');
  }
});

test('device timezones convert the fixed instant, including calendar rollover and fractional offsets', () => {
  assert.equal(buildTimeLocal(INSTANT, 'Asia/Seoul').label, '2026-11-04 12:39:00 GMT+9');
  assert.equal(buildTimeLocal(INSTANT, 'America/Los_Angeles').label, '2026-11-03 19:39:00 GMT-8');
  assert.equal(buildTimeLocal(INSTANT, 'Asia/Kathmandu').label, '2026-11-04 09:24:00 GMT+5:45');
  assert.equal(buildTimeLocal(INSTANT, 'America/St_Johns').label, '2026-11-04 00:09:00 GMT-3:30');
  assert.equal(buildTimeLocal(INSTANT, 'UTC').label, '2026-11-04 03:39:00 UTC');
  assert.equal(buildTimeLocal('2026-12-31T23:59:00.000Z', 'Asia/Seoul').label, '2027-01-01 08:59:00 GMT+9');
});

test('DST belongs to the build date, not today, and repeated fall-back hours remain distinguishable', () => {
  for (const [instant, label] of [
    ['2026-01-15T12:00:00.000Z', '2026-01-15 04:00:00 GMT-8'],
    ['2026-07-15T12:00:00.000Z', '2026-07-15 05:00:00 GMT-7'],
    ['2026-11-01T08:30:00.000Z', '2026-11-01 01:30:00 GMT-7'],
    ['2026-11-01T09:30:00.000Z', '2026-11-01 01:30:00 GMT-8'],
  ]) assert.equal(buildTimeLocal(instant, 'America/Los_Angeles').label, label);
});

test('omitting timezone uses the device default rather than forcing UTC', () => {
  const previous = process.env.TZ;
  try {
    process.env.TZ = 'Asia/Seoul';
    assert.equal(buildTimeLocal(INSTANT).label, '2026-11-04 12:39:00 GMT+9');
    process.env.TZ = 'America/Los_Angeles';
    assert.equal(buildTimeLocal(INSTANT).label, '2026-11-03 19:39:00 GMT-8');
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test('unsupported Intl, zone or offset formatting retains deterministic UTC', () => {
  const expected = buildTimeUtc(INSTANT).label;
  assert.equal(buildTimeLocal(INSTANT, 'Invalid/Zone').label, expected);
  for (const Intl of [undefined, {DateTimeFormat: class { constructor() { throw Error('unsupported'); } }}, {
    DateTimeFormat: class {
      resolvedOptions() { return {timeZone: 'Asia/Seoul'}; }
      formatToParts() { return [{type: 'year', value: '2026'}]; }
    },
  }]) {
    const helper = load('src/lib/build-time.ts', {Intl, Date: noCurrentClock});
    assert.equal(helper.buildTimeLocal(INSTANT).label, expected);
  }
});
