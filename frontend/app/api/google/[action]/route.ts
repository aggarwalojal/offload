import { NextRequest, NextResponse } from 'next/server';
import { authConfig, calendarBackend, verifiedSession } from '@/lib/server-auth';

type Context = { params: Promise<{ action: string }> };
const headers = { 'Cache-Control': 'no-store, private', 'Referrer-Policy': 'no-referrer' };

export async function GET(request: NextRequest, { params }: Context) {
  const { action } = await params;
  if (!['connection', 'events'].includes(action)) return new NextResponse('Not found', { status: 404 });
  const config = authConfig();
  const configured = !!config && !!process.env.GOOGLE_BACKEND_URL;
  let signedIn = false;
  let email: string | null = null;
  try {
    const session = await verifiedSession();
    if (!session) return NextResponse.json({ configured, signed_in: false, connected: false, tasks_connected: false, tasks_enabled: process.env.GOOGLE_ENABLE_TASKS === 'true' }, { status: action === 'events' ? 401 : 200, headers });
    signedIn = true;
    email = session.user.email ?? null;
    const query = new URLSearchParams();
    if (action === 'events') {
      for (const key of ['start_time', 'end_time']) {
        const values = request.nextUrl.searchParams.getAll(key);
        if (values.length !== 1 || !Number.isFinite(Date.parse(values[0]))) return NextResponse.json({ detail: 'A valid date range is required.' }, { status: 422, headers });
        query.set(key, values[0]);
      }
    }
    const backend = await calendarBackend(`${action}${query.size ? `?${query}` : ''}`, session.token);
    const result = await backend.json();
    return NextResponse.json({ ...result, configured, signed_in: true, email: session.user.email }, { status: backend.status, headers });
  } catch {
    return NextResponse.json({ detail: 'Calendar is unavailable. Check the backend setup or try again.', configured, signed_in: signedIn, email, connected: false }, { status: 503, headers });
  }
}

export async function DELETE(request: NextRequest, { params }: Context) {
  if ((await params).action !== 'connection') return new NextResponse('Not found', { status: 404 });
  const config = authConfig();
  if (!config || request.headers.get('origin') !== config.site) return new NextResponse('Invalid origin', { status: 403 });
  const session = await verifiedSession();
  if (!session) return NextResponse.json({ detail: 'Sign in first.' }, { status: 401, headers });
  try {
    const response = await calendarBackend('connection', session.token, { method: 'DELETE' });
    return NextResponse.json(await response.json(), { status: response.status, headers });
  } catch { return NextResponse.json({ detail: 'Could not disconnect Calendar. Try again.' }, { status: 503, headers }); }
}
