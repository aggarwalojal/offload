import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { authClient, authConfig, calendarBackend, clearSession, saveSession, verifiedSession } from '@/lib/server-auth';

type Context = { params: Promise<{ action: string }> };
const privateHeaders = { 'Cache-Control': 'no-store, private', 'Referrer-Policy': 'no-referrer' };
const calendarScopes = 'openid email https://www.googleapis.com/auth/calendar.events.owned https://www.googleapis.com/auth/calendar.freebusy';

export async function GET(request: NextRequest, { params }: Context) {
  const { action } = await params;
  const config = authConfig();
  if (action === 'status') {
    const session = await verifiedSession();
    return NextResponse.json({ configured: !!config && !!process.env.GOOGLE_BACKEND_URL, signed_in: !!session, email: session?.user.email ?? null }, { headers: privateHeaders });
  }
  if (!['login', 'callback'].includes(action)) return new NextResponse('Not found', { status: 404 });
  const site = config?.site ?? request.nextUrl.origin;
  function go(message: string) { return NextResponse.redirect(`${site}/?view=settings&connection=${message}`, { status: 303, headers: privateHeaders }); }
  if (!config || !process.env.GOOGLE_BACKEND_URL) return go('setup-required');
  const jar = await cookies();
  const supabase = createServerClient(config.url, config.key, {
    cookieOptions: { httpOnly: true, secure: config.secure, sameSite: 'lax', path: '/' },
    cookies: {
      getAll: () => jar.getAll(),
      setAll: values => {
        for (const { name, value, options } of values) {
          // Only PKCE verifier cookies are sent during login. Supabase's normal
          // session cookie may contain Google provider tokens after callback;
          // discard it and use our own HttpOnly app-session cookies instead.
          if (action === 'login' && name.includes('code-verifier')) jar.set(name, value, { ...options, httpOnly: true, secure: config.secure, sameSite: 'lax' });
          else jar.delete(name);
        }
      },
    },
  });
  if (action === 'login') {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google', options: {
        redirectTo: `${config.site}/api/auth/callback`, scopes: calendarScopes,
        queryParams: { access_type: 'offline', prompt: 'consent' },
      },
    });
    if (error || !data.url) return go('sign-in-failed');
    return NextResponse.redirect(data.url, { status: 303, headers: privateHeaders });
  }
  const codes = request.nextUrl.searchParams.getAll('code');
  if (codes.length !== 1 || request.nextUrl.searchParams.has('error')) return go('sign-in-failed');
  try {
    const { data, error } = await supabase.auth.exchangeCodeForSession(codes[0]);
    if (error || !data.session) return go('sign-in-failed');
    const session = data.session;
    await saveSession(session);
    if (!session.provider_token) return go('calendar-permission-required');
    const response = await calendarBackend('connection', session.access_token, {
      method: 'PUT', body: JSON.stringify({ access_token: session.provider_token, refresh_token: session.provider_refresh_token ?? null }),
    });
    return go(response.ok ? 'connected' : 'calendar-connection-failed');
  } catch { return go('calendar-connection-failed'); }
}

export async function POST(request: NextRequest, { params }: Context) {
  const { action } = await params;
  const config = authConfig();
  if (action !== 'logout') return new NextResponse('Not found', { status: 404 });
  if (!config || request.headers.get('origin') !== config.site) return new NextResponse('Invalid origin', { status: 403 });
  const session = await verifiedSession();
  if (session) {
    // Supabase logout uses this app's session; Google grant remains encrypted
    // for this user so the next sign-in can reconnect or explicitly disconnect.
    const client = authClient();
    await client.auth.admin.signOut(session.token, 'local');
  }
  await clearSession();
  return NextResponse.json({ signed_in: false }, { headers: privateHeaders });
}
