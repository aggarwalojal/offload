import { NextRequest, NextResponse } from 'next/server';
import { authConfig, calendarBackend, verifiedSession } from '@/lib/server-auth';
const headers = { 'Cache-Control': 'no-store, private' };
export async function POST(request: NextRequest) {
  const config = authConfig();
  if (!config || request.headers.get('origin') !== config.site) return NextResponse.json({ detail: 'Invalid origin.' }, { status: 403, headers });
  try {
    const session = await verifiedSession();
    if (!session) return NextResponse.json({ detail: 'Sign in to Offload first.' }, { status: 401, headers });
    const input = await request.json();
    if (typeof input.display_name !== 'string' || !/^[\p{L}\p{M} .'-]{1,60}$/u.test(input.display_name.trim())) return NextResponse.json({ detail: 'Enter your name using up to 60 characters.' }, { status: 422, headers });
    const response = await calendarBackend('profile', session.token, { method: 'PUT', body: JSON.stringify({ display_name: input.display_name.trim() }) });
    if (!response.ok) return NextResponse.json({ detail: 'Could not save your name. Try again.' }, { status: response.status, headers });
    return NextResponse.json(await response.json(), { headers });
  } catch { return NextResponse.json({ detail: 'Could not save your name. Try again.' }, { status: 503, headers }); }
}
