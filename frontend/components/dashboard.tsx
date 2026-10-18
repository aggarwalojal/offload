'use client';

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useCalendar } from '@/lib/use-calendar';
import { liveAnalytics } from '@/lib/calendar-data';
import { SettingsPanel } from './settings-panel';
import { Calendar, MessageCircle, Sparkles } from 'lucide-react';
import { activities as demoActivities, categories, timeLabel, type Activity, type Category } from '@/lib/mock-data';
import { ScreenTimeView } from './screen-time-view';
import { WhatsAppPhone } from './whatsapp-phone';
import { WhatsAppConnection } from './whatsapp-connection';
import { CategoryBadge, Logo } from './ui';

export default function Dashboard() {
  const calendar = useCalendar();
  const params = useSearchParams();
  const [settingsOpen, setSettingsOpen] = useState(params.get('view') === 'settings');
  const [rightTab, setRightTab] = useState<'simulator' | 'connect'>('simulator');
  const [demoItems, setDemoItems] = useState<Activity[]>(demoActivities);
  const live = calendar.connection.signed_in;
  const analytics = live ? liveAnalytics(calendar.items) : undefined;
  const activities = analytics?.todayItems ?? demoItems;

  const handleSimulatedMessage = (text: string) => {
    const rawClauses = text.split(/,(?![^()]*\))|\band\b/i).map(s => s.trim()).filter(Boolean);
    const clauses = rawClauses.length > 0 ? rawClauses : [text];
    const newItems: Activity[] = [];

    for (const clause of clauses) {
      const lower = clause.toLowerCase();
      let cat: Category = 'career';
      let title = clause.replace(/tomorrow|today|yesterday|at \d+|\d+ ?(am|pm)|next \w+|by \w+/gi, '').trim();
      if (!title) title = clause;

      if (lower.includes('delta') || lower.includes('kickoff') || lower.includes('project') || lower.includes('migration') || lower.includes('client') || lower.includes('work') || lower.includes('hcm')) {
        cat = 'career';
      } else if (lower.includes('sync') || lower.includes('meeting') || lower.includes('call') || lower.includes('sponsor') || lower.includes('team') || lower.includes('1:1') || lower.includes('catchup') || lower.includes('alignment')) {
        cat = 'social';
      } else if (lower.includes('payroll') || lower.includes('filing') || lower.includes('compliance') || lower.includes('tax') || lower.includes('audit') || lower.includes('admin') || lower.includes('ops') || lower.includes('report') || lower.includes('checklist')) {
        cat = 'admin';
      } else if (lower.includes('workout') || lower.includes('gym') || lower.includes('health') || lower.includes('run') || lower.includes('break') || lower.includes('wellness') || lower.includes('walk') || lower.includes('lunch')) {
        cat = 'health';
      } else if (lower.includes('training') || lower.includes('study') || lower.includes('learn') || lower.includes('course') || lower.includes('read') || lower.includes('cert') || lower.includes('skill')) {
        cat = 'academics';
      }

      // Resolve dates for upcoming week
      let start = new Date(Date.now() + 15 * 60000);
      let end = new Date(Date.now() + 75 * 60000);

      if (lower.includes('tomorrow') || lower.includes('monday') || lower.includes('mon')) {
        // Monday Oct 19, 1:00 PM – 2:00 PM
        start = new Date('2026-10-19T13:00:00-04:00');
        end = new Date('2026-10-19T14:00:00-04:00');
      } else if (lower.includes('wednesday') || lower.includes('wed')) {
        // Wednesday Oct 21, 10:00 AM – 11:00 AM
        start = new Date('2026-10-21T10:00:00-04:00');
        end = new Date('2026-10-21T11:00:00-04:00');
      } else if (lower.includes('friday') || lower.includes('fri')) {
        // Friday Oct 23, 2:00 PM – 3:30 PM
        start = new Date('2026-10-23T14:00:00-04:00');
        end = new Date('2026-10-23T15:30:00-04:00');
      }

      newItems.push({
        id: 'demo-' + Math.random().toString(36).substring(2, 9),
        title: title.charAt(0).toUpperCase() + title.slice(1),
        category: cat,
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        source: 'whatsapp',
        phase: 'upcoming',
      });
    }

    setDemoItems(prev => [...newItems, ...prev]);
  };

  return (
    <div className="offload-app">
      {/* 1. Sleek Top Navigation Bar */}
      <header className="offload-topbar">
        <div className="topbar-left">
          <Logo />
          <span className="brand-tagline">Workload & Commitment Intelligence for Implementation Teams</span>
        </div>

        <div className="topbar-center">
          <div className="date-pill">
            <Calendar size={13} className="text-pink-400" />
            <span>{analytics?.date ?? "Demo · Saturday, October 17"}</span>
          </div>
        </div>

        <div className="topbar-right">
          <div className="whatsapp-status-pill">
            <i className="status-dot-green" />
            <MessageCircle size={13} />
            <span>WhatsApp preview</span>
          </div>
          <button className="offload-connect-button" onClick={() => setSettingsOpen(!settingsOpen)} aria-expanded={settingsOpen}>{settingsOpen ? "Back to dashboard" : "Connect Google"}</button>
          <div className="profile-pill">
            <span className="profile-avatar">{live ? "You" : "O"}</span>
            <span className="profile-name">{calendar.connection.display_name ? `Hey, ${calendar.connection.display_name}` : live ? "Add your name in Settings" : "Demo workspace"}</span>
          </div>
        </div>
      </header>

      {/* 2. Main Workspace: Apple Screen Time (Left) + WhatsApp Phone (Right) */}
      <main className="offload-main">
        {live && !settingsOpen && !calendar.connection.display_name && <div className="offload-name-prompt"><span>What should Offload call you?</span><button className="connect-google" onClick={() => setSettingsOpen(true)}>Add your name</button></div>}
        {settingsOpen ? <SettingsPanel calendar={calendar} connectionMessage={params.get('connection')} /> : <>
        <div className="offload-data-status" role="status">{calendar.loading ? 'Checking your Google connections…' : live ? (calendar.connection.connected ? 'Your Google Calendar · Live schedule' : 'Connect Google Calendar to load your schedule.') : 'Demo workspace · Connect Google to see your own schedule.'}<button onClick={() => setSettingsOpen(true)}>Manage connections</button></div>
        {live && <p className="offload-sync-status" role="status">{calendar.refreshing ? 'Refreshing Google…' : calendar.lastUpdated ? `Updated ${calendar.lastUpdated.toLocaleTimeString()} · Refreshes every 15 seconds` : 'Waiting for Google data'} <button disabled={calendar.refreshing} onClick={() => void calendar.refresh()}>Refresh now</button></p>}
        {calendar.error && <p className="connection-error" role="alert">{calendar.error}</p>}
        <div className="offload-grid">
          {/* Left Column: Apple Screen Time Dashboard */}
          <section className="offload-analytics-col">
            <ScreenTimeView analytics={analytics} activities={activities} />
          </section>

          {/* Right Column: Interactive WhatsApp Widget & Today's Schedule */}
          <section className="offload-phone-col">
            <div className="phone-widget-wrapper">
              <div className="widget-header">
                <div>
                  <h2>{live ? "Live WhatsApp & Google Sync" : "WhatsApp Intelligence"}</h2>
                  <p>{live ? "Your real chat powers this workspace." : "Test in the interactive simulator or connect your real phone & Google."}</p>
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                  <button
                    type="button"
                    onClick={() => setRightTab('simulator')}
                    style={{
                      padding: '5px 12px',
                      borderRadius: '20px',
                      fontSize: '11px',
                      fontWeight: 600,
                      border: '1px solid',
                      borderColor: rightTab === 'simulator' ? '#F43F5E' : '#E2E8F0',
                      background: rightTab === 'simulator' ? '#FFF1F2' : '#FFFFFF',
                      color: rightTab === 'simulator' ? '#E11D48' : '#64748B',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    📱 Simulator
                  </button>
                  <button
                    type="button"
                    onClick={() => setRightTab('connect')}
                    style={{
                      padding: '5px 12px',
                      borderRadius: '20px',
                      fontSize: '11px',
                      fontWeight: 600,
                      border: '1px solid',
                      borderColor: rightTab === 'connect' ? '#10B981' : '#E2E8F0',
                      background: rightTab === 'connect' ? '#F0FDF4' : '#FFFFFF',
                      color: rightTab === 'connect' ? '#059669' : '#64748B',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    ⚡ Connect Live
                  </button>
                </div>
              </div>

              {/* The Phone Simulator or Live Connection Manager */}
              {rightTab === 'connect' || (live && rightTab !== 'simulator') ? (
                <div className="live-whatsapp-guide">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                    <h3 style={{ margin: 0 }}>Connect Live Services</h3>
                    <button
                      type="button"
                      className="quick-chip"
                      style={{ padding: '4px 10px', fontSize: '11px' }}
                      onClick={() => setRightTab('simulator')}
                    >
                      📱 Try Simulator
                    </button>
                  </div>
                  <p style={{ marginBottom: '16px', fontSize: '13px', lineHeight: 1.6 }}>
                    Connect your real Google account and WhatsApp phone. Real commitments and brain dumps you text will parse, check for conflicts, and schedule directly.
                  </p>

                  {/* 1. Google Account Connection Card */}
                  <div style={{ background: '#F8FAFC', padding: '16px', borderRadius: '16px', marginBottom: '14px', border: '1px solid #E2E8F0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div>
                        <strong style={{ fontSize: '14px', color: '#0F172A', display: 'block' }}>1. Google Calendar &amp; Tasks</strong>
                        <span style={{ fontSize: '12px', color: '#64748B' }}>
                          {calendar.connection.connected ? `Connected as ${calendar.connection.email}` : 'Sign in to sync your live events and to-dos.'}
                        </span>
                      </div>
                      <span className={`subtle-pill ${calendar.connection.connected ? 'active' : ''}`}>
                        {calendar.connection.connected ? 'Connected ✓' : 'Not Connected'}
                      </span>
                    </div>
                    {!calendar.connection.connected ? (
                      <form action="/api/auth/login" method="get">
                        <input type="hidden" name="service" value="calendar" />
                        <button
                          className="connect-google"
                          type="submit"
                          disabled={!calendar.connection.configured || calendar.loading}
                          style={{ width: '100%', marginTop: '8px' }}
                        >
                          Connect Google Calendar
                        </button>
                      </form>
                    ) : (
                      <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                        <button
                          type="button"
                          className="connect-google"
                          style={{ flex: 1, padding: '8px 12px', fontSize: '12px' }}
                          onClick={() => void calendar.refresh()}
                        >
                          Refresh Google Data
                        </button>
                      </div>
                    )}
                  </div>

                  {/* 2. WhatsApp Phone Integration Card */}
                  <div style={{ background: '#F0FDF4', padding: '16px', borderRadius: '16px', border: '1px solid #BBF7D0' }}>
                    <div style={{ marginBottom: '10px' }}>
                      <strong style={{ fontSize: '14px', color: '#166534', display: 'block' }}>2. WhatsApp Phone Integration</strong>
                      <span style={{ fontSize: '12px', color: '#15803D' }}>
                        Link your phone number to text plans directly into Offload.
                      </span>
                    </div>
                    <WhatsAppConnection
                      key={calendar.connection.email ?? 'anon'}
                      signedIn={calendar.connection.signed_in}
                      googleConnected={calendar.connection.connected || !!calendar.connection.tasks_connected}
                    />
                  </div>

                  <small style={{ marginTop: '14px', display: 'block', color: '#64748B', fontSize: '12px' }}>
                    Once connected, text your plans to WhatsApp (e.g., “Client kickoff with Delta tomorrow 2–3 PM”) and watch your dashboard update automatically.
                  </small>
                </div>
              ) : (
                <WhatsAppPhone
                  onMessageSent={handleSimulatedMessage}
                  onSwitchToLive={() => setRightTab('connect')}
                />
              )}

              {live && <section className="schedule-queue-card" aria-label="Google Tasks"><div className="queue-header"><h3>Your Google Tasks</h3><span>{calendar.tasks.length} to-dos</span></div><div className="queue-list">{calendar.connection.tasks_connected ? calendar.tasks.length ? calendar.tasks.map(task => <div className="queue-item" key={task.external_id}><div className="queue-item-left"><div><strong>{task.title}</strong><small>{task.due ? `Due ${task.due.slice(0, 10)}` : 'No due date'}</small></div></div></div>) : <p className="offload-empty">No open tasks. New WhatsApp tasks will appear here after Google sync.</p> : <p className="offload-empty">Connect Google Tasks in Settings to see your to-dos.</p>}</div></section>}
              {/* Today's Synced Schedule Card */}
              <div className="schedule-queue-card">
                <div className="queue-header">
                  <h3>{live ? "Today's Calendar Schedule" : "Sample Schedule"}</h3>
                  <span>{activities.length} items</span>
                </div>
                <div className="queue-list">{!activities.length && <p className="offload-empty">No timed events to show today.</p>}
                  {activities.slice(0, 5).map(act => (
                    <div key={act.id} className="queue-item">
                      <div className="queue-item-left">
                        <span className="queue-dot" style={{ backgroundColor: categories.find(c => c.id === act.category)?.color }} />
                        <div>
                          <strong>{act.title}</strong>
                          <small>{timeLabel(act.start_time)} – {timeLabel(act.end_time)}</small>
                        </div>
                      </div>
                      <CategoryBadge category={act.category} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </div>
        </>}
      </main>
    </div>
  );
}
