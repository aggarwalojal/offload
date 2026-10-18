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
import { CategoryBadge, Logo } from './ui';

export default function Dashboard() {
  const calendar = useCalendar();
  const params = useSearchParams();
  const [settingsOpen, setSettingsOpen] = useState(params.get('view') === 'settings');
  const [demoItems, setDemoItems] = useState<Activity[]>(demoActivities);
  const live = calendar.connection.signed_in;
  const analytics = live ? liveAnalytics(calendar.items) : undefined;
  const activities = analytics?.todayItems ?? demoItems;

  const handleSimulatedMessage = (text: string) => {
    const lower = text.toLowerCase();
    let cat: Category = 'career';
    let title = text.replace(/tomorrow|today|yesterday|at \d+|\d+ ?(am|pm)|next \w+/gi, '').trim();
    if (!title) title = text;

    if (lower.includes('delta') || lower.includes('kickoff') || lower.includes('project') || lower.includes('migration') || lower.includes('client') || lower.includes('work') || lower.includes('hcm')) {
      cat = 'career';
    } else if (lower.includes('sync') || lower.includes('meeting') || lower.includes('call') || lower.includes('sponsor') || lower.includes('team') || lower.includes('1:1') || lower.includes('catchup')) {
      cat = 'social';
    } else if (lower.includes('payroll') || lower.includes('filing') || lower.includes('compliance') || lower.includes('tax') || lower.includes('audit') || lower.includes('admin') || lower.includes('ops') || lower.includes('report')) {
      cat = 'admin';
    } else if (lower.includes('workout') || lower.includes('gym') || lower.includes('health') || lower.includes('run') || lower.includes('break') || lower.includes('wellness') || lower.includes('walk') || lower.includes('lunch')) {
      cat = 'health';
    } else if (lower.includes('training') || lower.includes('study') || lower.includes('learn') || lower.includes('course') || lower.includes('read') || lower.includes('cert') || lower.includes('skill')) {
      cat = 'academics';
    }

    const now = new Date();
    const start = new Date(now.getTime() + 15 * 60000);
    const end = new Date(start.getTime() + 60 * 60000);

    const newActivity: Activity = {
      id: 'demo-' + Date.now(),
      title: title.charAt(0).toUpperCase() + title.slice(1),
      category: cat,
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      source: 'whatsapp',
      phase: 'upcoming',
    };

    setDemoItems(prev => [newActivity, ...prev]);
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
                  <h2>{live ? "Send plans in WhatsApp" : "WhatsApp Brain Dump"}</h2>
                  <p>{live ? "Your real chat powers this workspace." : "Try the demo. Real Google sync uses your WhatsApp messages."}</p>
                </div>
                <span className="live-pill">
                  <Sparkles size={12} />
                  {live ? "GOOGLE SYNC" : "DEMO PREVIEW"}
                </span>
              </div>

              {/* The Phone Simulator */}
              {live ? <div className="live-whatsapp-guide"><h3>Text it. Offload it.</h3><p>Connect your Google services, then verify your WhatsApp number in Settings. Return to your WhatsApp chat and send your plans.</p><p>For example: “Client kickoff with Delta tomorrow 2–3 PM and review Vantage HCM migration checklist by Friday.”</p><button className="connect-google" onClick={() => setSettingsOpen(true)}>Manage WhatsApp &amp; Google</button><small>Once the agent confirms your message, Calendar events and Tasks refresh here automatically.</small></div> : <WhatsAppPhone onMessageSent={handleSimulatedMessage} />}

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
