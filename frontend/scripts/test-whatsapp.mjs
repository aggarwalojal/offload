// Execute the actual route handler with mocked session/provider boundaries.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../app/api/whatsapp/link/route.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
let session = { token: 'verified-user-token', user: { id: 'real-user' } };
let calls = [];
const env = { WHATSAPP_BACKEND_URL: 'https://whatsapp.example' };
const exported = {};
vm.runInNewContext(compiled.outputText, {
  exports: exported, URL, JSON, AbortSignal,
  process: { env },
  require: name => {
    if (name === 'next/server') return { NextResponse: { json: (data, options) => new Response(JSON.stringify(data), options) } };
    if (name === '@/lib/server-auth') return {
      authConfig: () => ({ site: 'https://dashboard.example' }),
      verifiedSession: async () => session,
    };
    throw new Error(`Unexpected import: ${name}`);
  },
  fetch: async (...args) => {
    calls.push(args);
    return Response.json({ url: 'https://wa.me/15551111111?text=LINK%20test', expires_in: 900 });
  },
});
const request = (origin = 'https://dashboard.example') => ({
  headers: new Headers({ origin }),
  json: async () => ({ timezone: 'Europe/London', user_id: 'attacker-chosen' }),
});

let response = await exported.POST(request('https://other.example'));
assert.equal(response.status, 403);
assert.equal(calls.length, 0);

session = null;
response = await exported.POST(request());
assert.equal(response.status, 401);
assert.equal(calls.length, 0);

session = { token: 'verified-user-token', user: { id: 'real-user' } };
response = await exported.POST(request());
assert.equal(response.status, 200);
assert.equal(response.headers.get('cache-control'), 'no-store, private');
assert.equal(calls[0][0], 'https://whatsapp.example/api/whatsapp/link');
assert.equal(calls[0][1].headers.Authorization, 'Bearer verified-user-token');
assert.deepEqual(JSON.parse(calls[0][1].body), { timezone: 'Europe/London' });
assert.equal(calls[0][1].redirect, 'error');
assert.equal((await response.json()).expires_in, 900);

calls = [];
env.WHATSAPP_BACKEND_URL = 'http://external.example';
assert.equal((await exported.GET(request())).status, 503);
assert.equal(calls.length, 0);
delete env.WHATSAPP_BACKEND_URL;
assert.equal((await exported.GET(request())).status, 503);
console.log('WhatsApp proxy checks passed: verified sessions, origin protection, identity isolation, HTTPS, and uncached responses.');
