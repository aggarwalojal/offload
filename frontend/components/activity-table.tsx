'use client';

import { useState } from 'react';
import { ArrowRight, CalendarDays, Check, MessageCircle, Search } from 'lucide-react';
import { activities, categories, durationMinutes, formatDuration, timeLabel, type Activity } from '@/lib/mock-data';
import { CategoryBadge, Panel } from './ui';

export function ActivityTable({ full = false, onViewAll, items = activities, live = false }: { full?: boolean; onViewAll?: () => void; items?: Activity[]; live?: boolean }) {
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
  const filtered = items.filter(a => (category === 'all' || a.category === category) && a.title.toLowerCase().includes(query.toLowerCase()));
  const rows = full ? filtered : filtered.slice(0, 4);
  return (
    <Panel className="activity-panel">
      <div className="panel-heading"><div><h2>Recent activities <span className="count-badge">{filtered.length}</span></h2><p>Your plans, organized automatically.</p></div><select aria-label="Filter activities by category" value={category} onChange={e => setCategory(e.target.value)}><option value="all">All categories</option>{categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      {full && <div className="activity-search"><Search size={16} /><input aria-label="Search activities" placeholder="Find something in your day…" value={query} onChange={e => setQuery(e.target.value)} /><span>{filtered.length} activities</span></div>}
      <div className="table-scroll"><table><caption className="sr-only">Planned activities</caption><thead><tr><th>ACTIVITY</th><th>CATEGORY</th><th>TIME</th><th>DURATION</th><th>STATUS</th></tr></thead><tbody>{rows.map(a => <tr key={a.id}><td><span className="task-icon">{a.source === 'whatsapp' ? <MessageCircle size={16} /> : <CalendarDays size={16} />}</span><span className="task-title">{a.title}<small>Added via {a.source === 'whatsapp' ? 'WhatsApp' : 'Google Calendar'}</small></span></td><td><CategoryBadge category={a.category} /></td><td>{live ? new Date(a.start_time).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : timeLabel(a.start_time)} – {live ? new Date(a.end_time).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : timeLabel(a.end_time)}</td><td className="task-duration">{formatDuration(durationMinutes(a))}</td><td><span className={`task-phase ${a.phase}`}>{a.phase === 'completed' && <Check size={11} />}{a.phase === 'completed' ? (live ? 'Ended' : 'Completed') : 'Upcoming'}</span></td></tr>)}</tbody></table></div>
      {rows.length === 0 && <div className="empty-state"><Search size={24} /><h3>No activities found</h3><p>Try another search or category.</p><button onClick={() => { setQuery(''); setCategory('all'); }}>Clear filters</button></div>}
      {!full && <button className="view-all" onClick={onViewAll}>View all activity <ArrowRight size={13} /></button>}
      {full && <div className="table-footer">Showing {rows.length} of {items.length} activities<span>{live ? 'Your Calendar · Local timezone' : 'Demo schedule · Eastern Time'}</span></div>}
    </Panel>
  );
}
