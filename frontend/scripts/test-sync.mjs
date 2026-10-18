// Exercise the hook's refresh lifecycle with mocked network/React boundaries.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../lib/use-calendar.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
const states = [], effects = [], timers = [], listeners = new Map();
let generation = 1, busy = false, eventFetches = 0, taskFetches = 0, visible = true;
const exported = {};
const lifecycle = { addEventListener: (key, fn) => listeners.set(key, fn), removeEventListener: key => listeners.delete(key) };
vm.runInNewContext(compiled.outputText, {
  exports: exported, Promise, Date, Error, URLSearchParams, Array,
  window: lifecycle, document: { ...lifecycle, get visibilityState() { return visible ? 'visible' : 'hidden'; } },
  setInterval: fn => { timers.push(fn); return 1; }, clearInterval: () => timers.pop(),
  require: name => {
    if (name === 'react') return {
      useCallback: fn => fn, useRef: value => ({ current: value }), useEffect: fn => effects.push(fn),
      useState: initial => { const index = states.length; states.push(initial); return [initial, value => { states[index] = value; }]; },
    };
    if (name === './calendar-data') return { calendarRange: () => ({ start_time: 'start', end_time: 'end' }), normalizeEvents: data => data };
    throw new Error(`Unexpected module ${name}`);
  },
  fetch: async url => {
    if (url === '/api/google/connection') return Response.json({ connected: true, tasks_connected: true, signed_in: true, configured: true });
    if (url.startsWith('/api/google/events')) {
      eventFetches++;
      if (busy) await new Promise(resolve => setTimeout(resolve, 10));
      return Response.json({ events: [{ external_id: `event-${generation}`, start: { dateTime: '2026-10-17T12:00:00Z' } }] });
    }
    if (url === '/api/google/tasks') { taskFetches++; return Response.json({ tasks: [{ external_id: `task-${generation}` }] }); }
    throw new Error(`Unexpected endpoint ${url}`);
  },
});
const tick = () => new Promise(resolve => setTimeout(resolve, 20));
const hook = exported.useCalendar();
const cleanup = effects[0]();
await tick();
assert.equal(eventFetches, 1); assert.equal(taskFetches, 1);
assert(states.some(value => Array.isArray(value) && value[0]?.external_id === 'task-1'));
generation = 2; timers[0](); await tick();
assert(states.some(value => Array.isArray(value) && value[0]?.external_id === 'task-2'));
assert(states.some(value => Array.isArray(value) && value[0]?.external_id === 'event-2'));
visible = false; timers[0](); await tick(); assert.equal(eventFetches, 2);
visible = true; listeners.get('focus')(); await tick(); assert.equal(eventFetches, 3);
busy = true; await Promise.all([hook.refresh(), hook.refresh()]); assert.equal(eventFetches, 4);
cleanup(); assert.equal(timers.length, 0); assert.equal(listeners.size, 0);
console.log('Live sync checks passed: Calendar and Tasks refresh, visible-tab polling, focus refresh, overlap prevention, and listener cleanup.');
