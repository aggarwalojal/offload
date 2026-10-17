'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { CalendarDays, ListTodo, LogOut, MessageCircle, ShieldCheck, Sparkles } from 'lucide-react';
import type { useCalendar } from '@/lib/use-calendar';
import { Panel } from './ui';

type CalendarState = ReturnType<typeof useCalendar>;
const messages: Record<string, string> = {
  connected: 'Google connected.',
  'calendar-connected': 'Google Calendar connected. Your schedule is ready.',
  'tasks-connected': 'Google Tasks connected. Your to-do list is ready.',
  'setup-required': 'The shared account service is being configured. Try again once setup is complete.',
  'sign-in-failed': 'Google sign-in was cancelled or could not finish. Please try again.',
  'calendar-permission-required': 'Sign in again and approve the requested Google permissions.',
  'calendar-connection-failed': 'You signed in, but the selected Google service could not connect. Keep existing permissions selected and try again.',
};

export function SettingsPanel({ calendar, connectionMessage }: { calendar: CalendarState; connectionMessage: string | null }) {
  const router = useRouter();
  const [digest, setDigest] = useState(true);
  const [recap, setRecap] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function disconnect() {
    setBusy(true); setError('');
    try {
      const response = await fetch('/api/google/connection', { method: 'DELETE' });
      if (!response.ok) throw new Error('Could not disconnect. Please try again.');
      await calendar.refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Please try again.'); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError('');
    try {
      const response = await fetch('/api/auth/logout', { method: 'POST' });
      if (!response.ok) throw new Error('Could not sign out. Try again.');
      await calendar.refresh();
      router.push('/');
      router.refresh();
      setBusy(false);
    } catch { setError('Could not sign out. Try again.'); setBusy(false); }
  }
  const status = calendar.connection;
  return <>
    {connectionMessage && messages[connectionMessage] && <p className="connection-result" role="status">{messages[connectionMessage]}</p>}
    <div className="settings-grid">
      <Panel className="preferences-panel"><div className="panel-heading"><div><h2>Your day, your way</h2><p>Preferences for a little less planning.</p></div><Sparkles size={18} /></div>
        <div className="settings-content">{[
          { title: 'Morning briefing', description: 'A simple look at what’s ahead, at 8:00 AM.', checked: digest, set: setDigest },
          { title: 'Evening recap', description: 'A moment to reflect on your day, at 9:00 PM.', checked: recap, set: setRecap },
        ].map(item => <div className="setting-row" key={item.title}><div><h3>{item.title}</h3><p>{item.description}</p></div><button role="switch" aria-checked={item.checked} aria-label={item.title} className={`toggle ${item.checked ? 'on' : ''}`} onClick={() => item.set(!item.checked)}><span /></button></div>)}
        <div className="setting-row"><div><h3>Timezone</h3><p>Your real Calendar uses your browser’s timezone.</p></div><span className="timezone">Local time</span></div>
        <p className="settings-note">Briefing preferences are previews. Messages aren’t scheduled yet.</p></div>
      </Panel>
      <Panel className="connections-panel"><div className="panel-heading"><div><h2>Your connected world</h2><p>One sign-in. A schedule that’s yours.</p></div></div><div className="settings-content">
        <div className="connection-row"><span className="feed-icon green"><MessageCircle size={19} /></span><div><h3>WhatsApp</h3><p>Messaging integration coming next.</p></div><span className="subtle-pill">Demo</span></div>
        {([
          { service: 'calendar', title: 'Google Calendar', description: 'Scheduled events and time analytics.', connected: status.connected, enabled: status.configured, Icon: CalendarDays, color: 'blue' },
          { service: 'tasks', title: 'Google Tasks', description: 'To-do items and deadlines.', connected: !!status.tasks_connected, enabled: status.configured && !!status.tasks_enabled, Icon: ListTodo, color: 'green' },
        ]).map(({ service, title, description, connected, enabled, Icon, color }) => <div key={service}>
          <div className="connection-row"><span className={`feed-icon ${color}`}><Icon size={19} /></span><div><h3>{title}</h3><p>{connected ? status.email : description}</p></div><span className="subtle-pill">{connected ? 'Connected' : 'Not connected'}</span></div>
          <div className="calendar-actions"><form action="/api/auth/login" method="get"><input type="hidden" name="service" value={service} /><button className="connect-google" type="submit" disabled={!enabled || busy || calendar.loading}>{connected ? `Reconnect ${title}` : `Connect ${title}`}</button></form>
          {!enabled && !calendar.loading && <p>{title} setup is not complete yet.</p>}</div>
        </div>)}
        <div className="calendar-actions">
          {(status.connected || status.tasks_connected) && <button disabled={busy} onClick={() => void disconnect()}>Disconnect Google account</button>}
          {status.signed_in && <button disabled={busy} onClick={() => void logout()}><LogOut size={13} />Sign out</button>}
        </div>
        {error && <p className="connection-error" role="alert">{error}</p>}
        <div className="privacy-note"><ShieldCheck size={18} /><p>Connect each service separately using the same Google account. Disconnecting the Google account removes both connections. Google tokens are encrypted on the backend. All-day events aren’t counted as hourly planned time.</p></div>
      </div></Panel>
    </div>
  </>;
}
