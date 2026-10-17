'use client';

import { useState, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';
import { liveAnalytics } from '@/lib/calendar-data';
import { useCalendar } from '@/lib/use-calendar';
import { Activity, ArrowDownToLine, ArrowUpRight, Bell, BookOpen, CalendarDays, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, Ellipsis, LayoutDashboard, MessageCircle, Settings, Sparkles, TrendingUp, X } from 'lucide-react';
import { activities as demoActivities, distribution as demoDistribution, demoDate, durationMinutes, formatDuration, type Activity as PlannedActivity, type View } from '@/lib/mock-data';
import { ActivityTable } from './activity-table';
import { AgentFeed } from './agent-feed';
import { SettingsPanel } from './settings-panel';
import { DistributionChart, WeeklyChart } from './time-charts';
import { Logo, Panel } from './ui';

function StatCard({ title, value, icon, children, className = '' }: { title: string; value: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return <Panel className={`stat-card ${className}`}><div className="stat-top"><span>{title}</span>{icon}</div><strong className="stat-value">{value}</strong><div className="stat-caption">{children}</div></Panel>;
}

function SummaryCards({ activities, data, live }: { activities: PlannedActivity[]; data: typeof demoDistribution; live: boolean }) {
  const totalMinutes = data.reduce((sum, item) => sum + item.minutes, 0);
  const busiestCategory = [...data].sort((a, b) => b.minutes - a.minutes)[0];
  const completed = activities.filter(a => a.phase === 'completed').length;
  return <div className="stats-grid">
    <StatCard title="Total planned hours" value={formatDuration(totalMinutes)} icon={<Clock3 size={19} />}><span className="trend"><TrendingUp size={12} /></span><span>{live ? "Overlaps counted once" : "Planned from your demo schedule"}</span><span className="spark-bars" aria-hidden="true">{[25, 40, 30, 60, 45, 75, 60, 85, 72, 100].map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</span></StatCard>
    <StatCard title="Busiest category" value={totalMinutes ? busiestCategory.name : "No events"} icon={<BookOpen size={19} />} className="busiest-card"><i className="tiny-dot" /><span>{formatDuration(busiestCategory.minutes)}</span><span className="separator">·</span><span>{(totalMinutes ? Math.round(busiestCategory.minutes / totalMinutes * 100) : 0)}% of your day</span><span className="mini-progress"><i style={{ width: `${(totalMinutes ? busiestCategory.minutes / totalMinutes * 100 : 0)}%` }} /></span></StatCard>
    <StatCard title="Number of activities" value={String(activities.length)} icon={<CheckCheck size={20} />}><span className="completed-label"><Check size={12} />{completed} {live ? 'ended' : 'completed'}</span><span className="separator">·</span><span>{activities.length - completed} coming up</span><span className="activity-dots" aria-hidden="true">{activities.map(a => <i key={a.id} className={a.phase} />)}</span></StatCard>
  </div>;
}

function exportActivities(activities: PlannedActivity[]) {
  const rows = [
    ['Activity', 'Category', 'Start', 'End', 'Duration (minutes)', 'Source', 'Status'],
    ...activities.map(a => [a.title, a.category, a.start_time, a.end_time, String(durationMinutes(a)), a.source, a.phase]),
  ];
  const csv = rows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'timeslice-activities.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Dashboard() {
  const params = useSearchParams();
  const [view, setView] = useState<View>(params.get('view') === 'settings' ? 'Settings' : 'Dashboard');
  const calendar = useCalendar();
  const live = calendar.connection.signed_in;
  const analytics = liveAnalytics(calendar.items);
  const activities = live ? analytics.todayItems : demoActivities;
  const data = live ? analytics.distribution : demoDistribution;
  const [notification, setNotification] = useState(false);
  const headings = {
    Dashboard: { title: 'Your time, in perspective', description: 'A clear picture of your day. Space for what matters most.' },
    Activity: { title: 'Every little thing, organized', description: 'All your plans in one place, straight from your conversations.' },
    Settings: { title: 'Make TimeSlice yours', description: 'A few thoughtful defaults for a day that feels like you.' },
  };
  function navigate(next: View) { setView(next); setNotification(false); }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <button className="brand-button" aria-label="TimeSlice dashboard" onClick={() => navigate('Dashboard')}><Logo /></button>
        <div className="workspace-switcher"><span className="workspace-avatar">O</span><div>Personal workspace<small>Make time for what matters</small></div><ChevronDown size={13} /></div>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">{[{ name: 'Dashboard' as const, icon: LayoutDashboard }, { name: 'Activity' as const, icon: Activity }, { name: 'Settings' as const, icon: Settings }].map(({ name, icon: Icon }) => <button key={name} aria-label={name} className={view === name ? 'active' : ''} aria-current={view === name ? 'page' : undefined} onClick={() => navigate(name)}><Icon size={18} /><span>{name}</span>{view === name && <i className="nav-indicator" />}</button>)}</nav>
        <div className="sidebar-bottom"><div className="sidebar-connection"><MessageCircle size={23} /><h3>Connected to your day</h3><p>Your WhatsApp. Your calendar.<br />Working better, together.</p><span><i />Preview the possibilities</span></div><button className="help-button" onClick={() => setNotification(true)}><CircleHelp size={16} /><span>A little help?</span><ArrowUpRight size={14} /></button><div className="profile"><span className="avatar">{live ? "You" : "TS"}</span><div>{calendar.connection.email ?? "Demo workspace"}<small>{live ? "Personal account" : "Connect your Calendar in Settings"}</small></div><button aria-label="Open account settings" onClick={() => navigate('Settings')}><Ellipsis size={18} /></button></div></div>
      </aside>
      <div className="main-shell">
        <header className="topbar"><div className="breadcrumb">Workspace<ChevronRight size={12} /><span>{view}</span></div><div className="topbar-actions"><span className="demo-tag">{live ? "YOUR WORKSPACE" : "DEMO WORKSPACE"}</span><span className="system-status"><i />{live ? "Your Google Calendar" : "Running on sample data"}</span><button className="notification-button" aria-label="Show notifications" aria-expanded={notification} onClick={() => setNotification(n => !n)}><Bell size={18} /><i /></button><button className="avatar small-avatar" aria-label="Open profile settings" onClick={() => navigate('Settings')}>{live ? "You" : "TS"}</button></div></header>
        <main id="main-content">
          <div className="page-heading"><div><div className="eyebrow"><i />A LITTLE MORE INTENTIONAL, EVERY DAY</div><h1>{headings[view].title}<span>.</span></h1><p>{headings[view].description}</p></div><button className="export-button" onClick={() => exportActivities(live ? calendar.items : demoActivities)}><ArrowDownToLine size={14} />Export overview</button></div>
          <div className={`account-banner ${calendar.error ? 'has-error' : ''}`} role="status"><div><strong>{calendar.loading ? 'Checking your Calendar…' : calendar.error ? 'Calendar needs attention' : calendar.connection.connected ? 'Your Calendar is connected' : live ? 'Connect your Calendar' : 'Make this dashboard yours'}</strong><p>{calendar.error || (calendar.connection.connected ? 'Times use your local timezone. Uncategorized events appear in Admin; all-day events are excluded from hourly totals.' : 'Sign in with Google to see your own schedule. Sample data is shown until you sign in.')}</p></div><button onClick={() => navigate('Settings')}>Settings <ChevronRight size={14} /></button>{calendar.connection.connected && <button disabled={calendar.loading} onClick={() => void calendar.refresh()}>Refresh</button>}</div>
          {view === 'Dashboard' && <>
            <div className="overview-heading"><div><h2>Today’s overview</h2><span>{live ? analytics.date : demoDate.replace(', 2026', '')}</span></div><span className="updated-label"><i />{live ? "Live Calendar · Local time" : "Demo day · Eastern Time"}</span></div>
            <SummaryCards activities={activities} data={data} live={live} />
            <div className="charts-grid"><DistributionChart data={data} live={live} /><WeeklyChart liveWeeks={live ? analytics.weeks : undefined} /></div>
            <div className="details-grid"><ActivityTable items={activities} live={live} onViewAll={() => navigate('Activity')} />{live ? <Panel className="live-calendar-note"><CalendarDays size={25} /><h2>Your schedule, connected.</h2><p>{calendar.connection.connected ? `${calendar.items.length} timed events loaded across this week and last week. ${calendar.allDayCount} all-day events are excluded from hourly analytics.` : 'Connect Google Calendar in Settings to load your schedule.'}</p><p>WhatsApp and AI activity will appear here when the shared backend is connected.</p></Panel> : <AgentFeed />}</div>
            <div className="daily-note"><span className="daily-note-icon"><Sparkles size={19} /></span><div><h3>You’re more than your to-do list.</h3><p>Your day has room for learning, ambition, and a little time for yourself. Keep it that way.</p></div><span className="note-decoration" aria-hidden="true">◔</span></div>
          </>}
          {view === 'Activity' && <><div className="activity-date"><CalendarDays size={15} />{live ? "Your Calendar activities" : demoDate}<span>{live ? "Times in your local timezone" : "All times in Eastern Time"}</span></div><ActivityTable full live={live} items={live ? calendar.items : demoActivities} /></>}
          <div hidden={view !== 'Settings'}><SettingsPanel calendar={calendar} connectionMessage={params.get("connection")} /></div>
          <footer className="page-footer"><span><span className="footer-symbol">◔</span>Made for a life beyond your calendar.</span><span>Planned time, not actual time tracked <Sparkles size={12} /></span></footer>
        </main>
      </div>
      {notification && <aside className="notification-popover" aria-label="Workspace notification"><button className="popover-close" aria-label="Close notification" onClick={() => setNotification(false)}><X size={16} /></button><span className="notification-icon"><Sparkles size={20} /></span><h2>A little less planning.<br />A little more living.</h2><p>Explore your time, filter your activities, and watch the simulated AI feed. Export your sample schedule whenever you like.</p><small>Connect your own Google Calendar from Settings. The WhatsApp activity feed is simulated.</small></aside>}
    </div>
  );
}
