'use client';

import { useState } from 'react';
import { ChevronLeft, ChevronRight, Sparkles, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { categories, distribution, formatDuration, totalMinutes, weeks } from '@/lib/mock-data';
import { Panel } from './ui';

const tooltipStyle = { background: '#242a3c', border: '1px solid #3b435b', borderRadius: 10, color: '#f4f2ff', fontSize: 12 };

export function DistributionChart() {
  return (
    <Panel className="distribution-panel">
      <div className="panel-heading"><div><h2>A day in slices</h2><p>Where your time is going today.</p></div><span className="subtle-pill">Today</span></div>
      <div className="donut-layout">
        <div className="donut-container" role="img" aria-label="Today's planned workload: Client Implementation, Compliance, Stakeholders, Product Enablement, and Deep Work.">
          <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 230, height: 230 }}>
            <PieChart><Pie data={distribution} dataKey="minutes" nameKey="name" innerRadius="74%" outerRadius="96%" paddingAngle={4} cornerRadius={5} stroke="none" startAngle={90} endAngle={-270}>
              {distribution.map(c => <Cell key={c.id} fill={c.color} />)}
            </Pie><Tooltip formatter={v => [formatDuration(Number(v)), 'Planned time']} contentStyle={tooltipStyle} itemStyle={{ color: '#fff' }} /></PieChart>
          </ResponsiveContainer>
          <div className="donut-center"><span>TOTAL PLANNED</span><strong>9<span>h</span> 30<span>m</span></strong><small><i />Workload Allocated</small></div>
        </div>
        <div className="distribution-legend">{distribution.map(c => <div key={c.id}><i style={{ background: c.color }} /><span>{c.name}</span><strong>{formatDuration(c.minutes)}</strong><small>{Math.round(c.minutes / totalMinutes * 100)}%</small></div>)}</div>
      </div>
      <div className="chart-insight"><Sparkles size={15} /><p>Client Commitments Balanced. <span>Deliverables and stakeholder syncs fully aligned.</span></p></div>
    </Panel>
  );
}

export function WeeklyChart() {
  const [weekIndex, setWeekIndex] = useState(1);
  const week = weeks[weekIndex];
  const total = week.data.reduce((sum, day) => sum + categories.reduce((n, c) => n + day[c.id], 0), 0) * 60;
  return (
    <Panel className="weekly-panel">
      <div className="panel-heading"><div><h2>Your week at a glance</h2><p>Small slices. A bigger picture.</p></div><div className="week-switcher"><button aria-label="Previous week" disabled={weekIndex === 0} onClick={() => setWeekIndex(0)}><ChevronLeft size={14} /></button><span>{week.label}</span><button aria-label="Next week" disabled={weekIndex === 1} onClick={() => setWeekIndex(1)}><ChevronRight size={14} /></button></div></div>
      <div className="weekly-summary"><strong>{formatDuration(total)}</strong><span>planned this week</span>{weekIndex === 1 && <span className="trend"><TrendingUp size={13} />11.1%<span className="sr-only">more than last week</span></span>}</div>
      <div className="weekly-chart" role="img" aria-label={`Stacked planned hours by category from Monday to Sunday, ${week.label}. Total ${formatDuration(total)}.`}>
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 400, height: 180 }}>
          <BarChart data={week.data} barSize={30} margin={{ left: -22, right: 4, top: 10, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#30374a" strokeDasharray="3 5" />
            <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: '#8e99b0', fontSize: 10 }} dy={8} />
            <YAxis domain={[0, 12]} ticks={[0, 3, 6, 9, 12]} tickFormatter={v => `${v}h`} axisLine={false} tickLine={false} tick={{ fill: '#75819a', fontSize: 10 }} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: '#fff' }} cursor={{ fill: '#ffffff05' }} formatter={(v, name) => [formatDuration(Number(v) * 60), categories.find(c => c.id === name)?.name ?? name]} />
            {categories.map((c, i) => <Bar key={c.id} dataKey={c.id} stackId="time" fill={c.color} radius={i === 4 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="week-legend">{categories.map(c => <span key={c.id}><i style={{ background: c.color }} />{c.name}</span>)}</div>
    </Panel>
  );
}
