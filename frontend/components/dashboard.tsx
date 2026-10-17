'use client';

import { useState } from 'react';
import { Bell, Calendar, Check, CheckCheck, Clock, MessageCircle, Sparkles } from 'lucide-react';
import { activities, categories, formatDuration, timeLabel, totalMinutes } from '@/lib/mock-data';
import { ScreenTimeView } from './screen-time-view';
import { WhatsAppPhone } from './whatsapp-phone';
import { CategoryBadge, Logo } from './ui';

export default function Dashboard() {
  const [notification, setNotification] = useState(false);

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
            <span>Saturday, October 17</span>
          </div>
        </div>

        <div className="topbar-right">
          <div className="whatsapp-status-pill">
            <i className="status-dot-green" />
            <MessageCircle size={13} />
            <span>WhatsApp Sandbox Live</span>
          </div>
          <div className="profile-pill">
            <span className="profile-avatar">JC</span>
            <span className="profile-name">Jia</span>
          </div>
        </div>
      </header>

      {/* 2. Main Workspace: Apple Screen Time (Left) + WhatsApp Phone (Right) */}
      <main className="offload-main">
        <div className="offload-grid">
          {/* Left Column: Apple Screen Time Dashboard */}
          <section className="offload-analytics-col">
            <ScreenTimeView />
          </section>

          {/* Right Column: Interactive WhatsApp Widget & Today's Schedule */}
          <section className="offload-phone-col">
            <div className="phone-widget-wrapper">
              <div className="widget-header">
                <div>
                  <h2>WhatsApp Brain Dump</h2>
                  <p>Send a stream of consciousness text to offload.</p>
                </div>
                <span className="live-pill">
                  <Sparkles size={12} />
                  LIVE AI AGENT
                </span>
              </div>

              {/* The Phone Simulator */}
              <WhatsAppPhone />

              {/* Today's Synced Schedule Card */}
              <div className="schedule-queue-card">
                <div className="queue-header">
                  <h3>Today's Synced Schedule</h3>
                  <span>{activities.length} items</span>
                </div>
                <div className="queue-list">
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
      </main>
    </div>
  );
}
