import { NextRequest, NextResponse } from 'next/server';
import { authConfig, verifiedSession } from '@/lib/server-auth';

const headers = { 'Cache-Control': 'no-store, private', 'Referrer-Policy': 'no-referrer' };

async function proxy(request: NextRequest, method: 'GET' | 'POST') {
  const config = authConfig();
  if (method === 'POST' && (!config || request.headers.get('origin') !== config.site)) {
    return NextResponse.json({ detail: 'Invalid origin.' }, { status: 403, headers });
  }
  try {
    const session = await verifiedSession();
    if (!session) return NextResponse.json({ detail: 'Connect Google first.' }, { status: 401, headers });
    const base = process.env.WHATSAPP_BACKEND_URL;
    if (!base) return NextResponse.json({ detail: 'WhatsApp connection setup is not complete.' }, { status: 503, headers });
    const url = new URL(base);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
      throw new Error('WhatsApp backend needs HTTPS.');
    }
    let body: string | undefined;
    if (method === 'POST') {
      const input = await request.json();
      body = JSON.stringify({ timezone: input.timezone });
    }
    const upstream = await fetch(`${url.origin}/api/whatsapp/link`, {
      method, body, cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15000),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.token}` },
    });
    const result = await upstream.json();
    return NextResponse.json(upstream.ok ? result : { detail: 'Could not connect WhatsApp. Try again.' }, { status: upstream.status, headers });
  } catch {
    return NextResponse.json({ detail: 'WhatsApp connection is unavailable. Try again.' }, { status: 503, headers });
  }
}

export async function GET(request: NextRequest) { return proxy(request, 'GET'); }
export async function POST(request: NextRequest) { return proxy(request, 'POST'); }
