'use client';

import { useState, type ReactNode } from 'react';
import { Activity, ArrowDownToLine, ArrowUpRight, Bell, BookOpen, CalendarDays, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, Ellipsis, LayoutDashboard, MessageCircle, Settings, Sparkles, TrendingUp, X } from 'lucide-react';
import { activities, busiestCategory, demoDate, durationMinutes, formatDuration, totalMinutes, type View } from '@/lib/mock-data';
import { ActivityTable } from './activity-table';
import { AgentFeed } from './agent-feed';
import { SettingsPanel } from './settings-panel';
import { DistributionChart, WeeklyChart } from './time-charts';
import { Logo, Panel } from './ui';

function StatCard({ title, value, icon, children, className = '' }: { title: string; value: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return <Panel className={`stat-card ${className}`}><div className="stat-top"><span>{title}</span>{icon}</div><strong className="stat-value">{value}</strong><div className="stat-caption">{children}</div></Panel>;
}

function SummaryCards() {
  const completed = activities.filter(a => a.phase === 'completed').length;
  return <div className="stats-grid">
    <StatCard title="Total planned hours" value={formatDuration(totalMinutes)} icon={<Clock3 size={19} />}><span className="trend"><TrendingUp size={12} />12%</span><span>vs. demo daily average</span><span className="spark-bars" aria-hidden="true">{[25, 40, 30, 60, 45, 75, 60, 85, 72, 100].map((height, i) => <i key={i} style={{ height: `${height}%` }} />)}</span></StatCard>
    <StatCard title="Busiest category" value={busiestCategory.name} icon={<BookOpen size={19} />} className="busiest-card"><i className="tiny-dot" /><span>{formatDuration(busiestCategory.minutes)}</span><span className="separator">·</span><span>{Math.round(busiestCategory.minutes / totalMinutes * 100)}% of your day</span><span className="mini-progress"><i style={{ width: `${busiestCategory.minutes / totalMinutes * 100}%` }} /></span></StatCard>
    <StatCard title="Number of activities" value={String(activities.length)} icon={<CheckCheck size={20} />}><span className="completed-label"><Check size={12} />{completed} completed</span><span className="separator">·</span><span>{activities.length - completed} coming up</span><span className="activity-dots" aria-hidden="true">{activities.map(a => <i key={a.id} className={a.phase} />)}</span></StatCard>
  </div>;
}

function exportActivities() {
  const rows = [
    ['Activity', 'Category', 'Start', 'End', 'Duration (minutes)', 'Source', 'Status'],
    ...activities.map(a => [a.title, a.category, a.start_time, a.end_time, String(durationMinutes(a)), a.source, a.phase]),
  ];
  const csv = rows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'timeslice-demo-2026-10-17.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Dashboard() {
  const [view, setView] = useState<View>('Dashboard');
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
        <div className="sidebar-bottom"><div className="sidebar-connection"><MessageCircle size={23} /><h3>Connected to your day</h3><p>Your WhatsApp. Your calendar.<br />Working better, together.</p><span><i />Preview the possibilities</span></div><button className="help-button" onClick={() => setNotification(true)}><CircleHelp size={16} /><span>A little help?</span><ArrowUpRight size={14} /></button><div className="profile"><span className="avatar">OJ</span><div>Ojal Aggarwal<small>Personal account</small></div><button aria-label="Open account settings" onClick={() => navigate('Settings')}><Ellipsis size={18} /></button></div></div>
      </aside>
      <div className="main-shell">
        <header className="topbar"><div className="breadcrumb">Workspace<ChevronRight size={12} /><span>{view}</span></div><div className="topbar-actions"><span className="demo-tag">DEMO WORKSPACE</span><span className="system-status"><i />Running on sample data</span><button className="notification-button" aria-label="Show notifications" aria-expanded={notification} onClick={() => setNotification(n => !n)}><Bell size={18} /><i /></button><button className="avatar small-avatar" aria-label="Open profile settings" onClick={() => navigate('Settings')}>OJ</button></div></header>
        <main id="main-content">
          <div className="page-heading"><div><div className="eyebrow"><i />A LITTLE MORE INTENTIONAL, EVERY DAY</div><h1>{headings[view].title}<span>.</span></h1><p>{headings[view].description}</p></div><button className="export-button" onClick={exportActivities}><ArrowDownToLine size={14} />Export overview</button></div>
          {view === 'Dashboard' && <>
            <div className="overview-heading"><div><h2>Today’s overview</h2><span>{demoDate.replace(', 2026', '')}</span></div><span className="updated-label"><i />Demo day · Eastern Time</span></div>
            <SummaryCards />
            <div className="charts-grid"><DistributionChart /><WeeklyChart /></div>
            <div className="details-grid"><ActivityTable onViewAll={() => navigate('Activity')} /><AgentFeed /></div>
            <div className="daily-note"><span className="daily-note-icon"><Sparkles size={19} /></span><div><h3>You’re more than your to-do list.</h3><p>Your day has room for learning, ambition, and a little time for yourself. Keep it that way.</p></div><span className="note-decoration" aria-hidden="true">◔</span></div>
          </>}
          {view === 'Activity' && <><div className="activity-date"><CalendarDays size={15} />{demoDate}<span>All times in Eastern Time</span></div><ActivityTable full /></>}
          <div hidden={view !== 'Settings'}><SettingsPanel /></div>
          <footer className="page-footer"><span><span className="footer-symbol">◔</span>Made for a life beyond your calendar.</span><span>Planned time, not actual time tracked <Sparkles size={12} /></span></footer>
        </main>
      </div>
      {notification && <aside className="notification-popover" aria-label="Workspace notification"><button className="popover-close" aria-label="Close notification" onClick={() => setNotification(false)}><X size={16} /></button><span className="notification-icon"><Sparkles size={20} /></span><h2>A little less planning.<br />A little more living.</h2><p>Explore your time, filter your activities, and watch the simulated AI feed. Export your sample schedule whenever you like.</p><small>This demo doesn’t connect to external accounts.</small></aside>}
    </div>
  );
}
