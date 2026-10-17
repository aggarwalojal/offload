import 'server-only';
import { createClient, type Session, type User } from '@supabase/supabase-js';
import { cookies } from 'next/headers';

const accessCookie = 'timeslice_access';
const refreshCookie = 'timeslice_refresh';

export function authConfig() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_PUBLISHABLE_KEY;
  const site = process.env.TIMESLICE_SITE_URL;
  if (!url || !key || !site) return null;
  try {
    const parsed = new URL(site);
    const db = new URL(url);
    if (db.protocol !== 'https:' || db.pathname !== '/' || db.search || db.hash || db.username) return null;
    if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname))) return null;
    return { url, key, site: parsed.origin, secure: parsed.protocol === 'https:' };
  } catch { return null; }
}

export function authClient() {
  const config = authConfig();
  if (!config) throw new Error('Account setup is not complete.');
  return createClient(config.url, config.key, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } });
}

export async function saveSession(session: Pick<Session, 'access_token' | 'refresh_token' | 'expires_in'>) {
  const jar = await cookies();
  const options = { httpOnly: true, secure: authConfig()!.secure, sameSite: 'lax' as const, path: '/' };
  // These are Supabase app-session tokens, not Google provider credentials.
  jar.set(accessCookie, session.access_token, { ...options, maxAge: session.expires_in });
  jar.set(refreshCookie, session.refresh_token, { ...options, maxAge: 60 * 60 * 24 * 30 });
}

export async function clearSession() {
  const jar = await cookies();
  jar.delete(accessCookie);
  jar.delete(refreshCookie);
}

export async function verifiedSession(): Promise<{ token: string; user: User } | null> {
  if (!authConfig()) return null;
  const jar = await cookies();
  const client = authClient();
  const access = jar.get(accessCookie)?.value;
  if (access) {
    const { data, error } = await client.auth.getUser(access);
    if (!error && data.user) return { token: access, user: data.user };
  }
  const refresh = jar.get(refreshCookie)?.value;
  if (!refresh) return null;
  const { data, error } = await client.auth.refreshSession({ refresh_token: refresh });
  if (error || !data.session) { await clearSession(); return null; }
  // Validate the refreshed session with the auth server as well.
  const verified = await client.auth.getUser(data.session.access_token);
  if (verified.error || !verified.data.user) { await clearSession(); return null; }
  await saveSession(data.session);
  return { token: data.session.access_token, user: verified.data.user };
}

export async function calendarBackend(path: string, token: string, options: RequestInit = {}) {
  const value = process.env.GOOGLE_BACKEND_URL;
  if (!value) throw new Error('Calendar backend is not configured.');
  const url = new URL(value);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) throw new Error('Calendar backend needs HTTPS.');
  return fetch(`${url.origin}/api/google/${path}`, {
    ...options, cache: 'no-store', redirect: 'error',
    signal: AbortSignal.timeout(30000),
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  });
}
