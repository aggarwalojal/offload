'use client';

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useCalendar } from '@/lib/use-calendar';
import { liveAnalytics } from '@/lib/calendar-data';
import { SettingsPanel } from './settings-panel';
import { Calendar, MessageCircle, Sparkles } from 'lucide-react';
import { activities as demoActivities, categories, timeLabel } from '@/lib/mock-data';
import { ScreenTimeView } from './screen-time-view';
import { WhatsAppPhone } from './whatsapp-phone';
import { CategoryBadge, Logo } from './ui';

export default function Dashboard() {
  const calendar = useCalendar();
  const params = useSearchParams();
  const [settingsOpen, setSettingsOpen] = useState(params.get('view') === 'settings');
  const live = calendar.connection.signed_in;
  const analytics = live ? liveAnalytics(calendar.items) : undefined;
  const activities = analytics?.todayItems ?? demoActivities;

  return (
    <div className="offload-app">
      {/* 1. Sleek Top Navigation Bar */}
      <header className="offload-topbar">
        <div className="topbar-left">
          <Logo />
          <span className="brand-tagline">Screen Time for your real life</span>
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
            <span className="profile-name">{calendar.connection.email ?? "Demo workspace"}</span>
          </div>
        </div>
      </header>

      {/* 2. Main Workspace: Apple Screen Time (Left) + WhatsApp Phone (Right) */}
      <main className="offload-main">
        {settingsOpen ? <SettingsPanel calendar={calendar} connectionMessage={params.get('connection')} /> : <>
        <div className="offload-data-status" role="status">{calendar.loading ? 'Checking your Google connections…' : live ? (calendar.connection.connected ? 'Your Google Calendar · Live schedule' : 'Connect Google Calendar to load your schedule.') : 'Demo workspace · Connect Google to see your own schedule.'}<button onClick={() => setSettingsOpen(true)}>Manage connections</button></div>
        {calendar.error && <p className="connection-error" role="alert">{calendar.error}</p>}
        <div className="offload-grid">
          {/* Left Column: Apple Screen Time Dashboard */}
          <section className="offload-analytics-col">
            <ScreenTimeView analytics={analytics} />
          </section>

          {/* Right Column: Interactive WhatsApp Widget & Today's Schedule */}
          <section className="offload-phone-col">
            <div className="phone-widget-wrapper">
              <div className="widget-header">
                <div>
                  <h2>WhatsApp Brain Dump</h2>
                  <p>Try the demo. Real Google sync uses your WhatsApp messages.</p>
                </div>
                <span className="live-pill">
                  <Sparkles size={12} />
                  DEMO PREVIEW
                </span>
              </div>

              {/* The Phone Simulator */}
              <WhatsAppPhone />

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
