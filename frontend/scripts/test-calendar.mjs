// Pure analytics checks, with TypeScript compiled into a temporary test directory.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
process.env.TZ = 'America/New_York';
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'timeslice-analytics-'));
try {
  for (const name of ['mock-data', 'calendar-data']) {
    const source = fs.readFileSync(path.join(__dirname, '../lib', name + '.ts'), 'utf8');
    const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
    fs.writeFileSync(path.join(output, name + '.js'), compiled.outputText);
  }
  const { default: { categoryMinutes, normalizeEvents, calendarRange, liveAnalytics } } = await import(pathToFileURL(path.join(output, 'calendar-data.js')).href);
  const event = (id, category, start, end) => ({ id, title: id, category, start_time: start, end_time: end, source: 'calendar', phase: 'upcoming' });
  const start = new Date('2026-10-17T00:00:00-04:00');
  const end = new Date('2026-10-18T00:00:00-04:00');
  const first = event('first', 'academics', '2026-10-17T09:00:00-04:00', '2026-10-17T11:00:00-04:00');
  const second = event('second', 'career', '2026-10-17T10:00:00-04:00', '2026-10-17T12:00:00-04:00');
  const overlap = categoryMinutes([first, second], start, end);
  assert.equal(overlap.academics, 90);
  assert.equal(overlap.career, 90);
  assert.equal(Object.values(overlap).reduce((a, b) => a + b, 0), 180);
  const duplicate = categoryMinutes([first, { ...first, id: 'duplicate' }], start, end);
  assert.equal(duplicate.academics, 120);
  const crossing = event('overnight', 'health', '2026-10-16T23:30:00-04:00', '2026-10-17T00:30:00-04:00');
  assert.equal(categoryMinutes([crossing], start, end).health, 30);
  const raw = { external_id: 'real', title: 'My event', category: null, start: { dateTime: first.start_time }, end: { dateTime: first.end_time } };
  const normalized = normalizeEvents([raw, { ...raw, external_id: 'all-day', start: { date: '2026-10-17' }, end: { date: '2026-10-18' } }, { ...raw, status: 'cancelled' }, { ...raw, transparency: 'transparent' }]);
  assert.equal(normalized.length, 1);
  assert.equal(normalized[0].category, 'admin');
  const range = calendarRange(new Date('2026-10-17T12:00:00-04:00'));
  assert.equal(range.start_time, '2026-10-05T04:00:00.000Z');
  assert.equal(range.end_time, '2026-10-19T04:00:00.000Z');
  assert.equal(liveAnalytics([crossing, first], new Date('2026-10-17T12:00:00-04:00')).todayItems.length, 2);
  const dstStart = new Date('2026-11-01T00:00:00-04:00');
  const dstEnd = new Date('2026-11-02T00:00:00-05:00');
  const dst = event('dst', 'health', '2026-11-01T01:00:00-04:00', '2026-11-01T02:00:00-05:00');
  assert.equal(categoryMinutes([dst], dstStart, dstEnd).health, 120);
  console.log('Calendar analytics checks passed: overlap union, duplicate categories, midnight clipping, all-day exclusion, category fallback, week range, and DST.');
} finally { fs.rmSync(output, { recursive: true, force: true }); }
