'use client';

import type { liveAnalytics } from '@/lib/calendar-data';
import { useState } from 'react';
import { ChevronLeft, ChevronRight, Clock, Sparkles, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { categories, distribution as demoDistribution, durationMinutes, formatDuration, weeks as demoWeeks, type Activity, type Category } from '@/lib/mock-data';

const tooltipStyle = {
  background: '#FFFFFF',
  border: '1px solid #F2E6EC',
  borderRadius: 14,
  color: '#191122',
  fontSize: 12,
  fontWeight: 600,
  boxShadow: '0 10px 25px -5px rgba(244, 63, 94, 0.15), 0 2px 6px rgba(0, 0, 0, 0.04)',
};

export function ScreenTimeView({
  analytics,
  activities: passedActivities,
}: {
  analytics?: ReturnType<typeof liveAnalytics>;
  activities?: Activity[];
}) {
  const calculatedDistribution = passedActivities
    ? categories.map(cat => ({
        ...cat,
        minutes: passedActivities
          .filter(a => a.category === cat.id)
          .reduce((sum, a) => sum + durationMinutes(a), 0),
      }))
    : demoDistribution;

  const distribution = analytics?.distribution ?? calculatedDistribution;

  const dynamicWeeks = passedActivities && !analytics
    ? demoWeeks.map((w, idx) => {
        if (idx === 1) {
          return {
            ...w,
            data: w.data.map(d => {
              if (d.day === 'Sat') {
                const hoursByCategory: Record<Category, number> = {
                  career: 0,
                  social: 0,
                  admin: 0,
                  health: 0,
                  academics: 0,
                };
                for (const a of passedActivities) {
                  hoursByCategory[a.category] = (hoursByCategory[a.category] || 0) + durationMinutes(a) / 60;
                }
                return { day: 'Sat', ...hoursByCategory };
              }
              return d;
            }),
          };
        }
        return w;
      })
    : demoWeeks;

  const weeks = analytics?.weeks ?? dynamicWeeks;
  const totalMinutes = distribution.reduce((sum, item) => sum + item.minutes, 0);
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null);
  const [weekIndex, setWeekIndex] = useState(1);
  const week = weeks[weekIndex];

  // Sort categories by time spent descending (Apple Screen Time "Most Used" pattern)
  const rankedCategories = [...distribution].sort((a, b) => b.minutes - a.minutes);
  // Dynamically show categories that have allocated time based on what you input
  const activeCategories = rankedCategories.filter(cat => cat.minutes > 0);
  const categoriesToShow = activeCategories.length > 0 ? activeCategories : rankedCategories;

  return (
    <div className="screentime-container">
      {/* 1. Main Daily Screen Time Card */}
      <div className="screentime-card">
        <div className="screentime-header">
          <div className="screentime-icon-wrapper">
            <Clock size={20} className="text-pink-400" />
          </div>
          <div>
            <span className="screentime-caption">TODAY’S SCHEDULED WORKLOAD</span>
            <div className="screentime-hero-stat">
              <h1>{formatDuration(totalMinutes)}</h1>
              <span className="screentime-trend-pill">
                <TrendingUp size={13} />
                {analytics ? 'Calendar time' : '+14% from target'}
              </span>
            </div>
          </div>
        </div>

        {/* 2. Apple Screen Time Signature Segmented Horizontal Bar */}
        <div className="screentime-segmented-bar" role="img" aria-label="Daily time distribution bar">
          {distribution.map(cat => {
            const pct = (totalMinutes ? cat.minutes / totalMinutes : 0) * 100;
            if (pct <= 0) return null;
            return (
              <div
                key={cat.id}
                className="screentime-segment"
                style={{
                  width: `${pct}%`,
                  backgroundColor: cat.color,
                  boxShadow: `0 0 12px ${cat.color}66`,
                }}
                title={`${cat.name}: ${formatDuration(cat.minutes)} (${Math.round(pct)}%)`}
              />
            );
          })}
        </div>

        {/* 3. Category Legend Badges */}
        <div className="screentime-badges-row">
          {categories.map(c => {
            const data = distribution.find(d => d.id === c.id);
            const mins = data ? data.minutes : 0;
            return (
              <button
                key={c.id}
                className={`screentime-badge-chip ${selectedCategory === c.id ? 'active' : ''}`}
                onClick={() => setSelectedCategory(selectedCategory === c.id ? null : c.id)}
              >
                <i style={{ backgroundColor: c.color }} />
                <span>{c.name}</span>
                <strong>{formatDuration(mins)}</strong>
              </button>
            );
          })}
        </div>

        {/* 4. Weekly Trend Chart */}
        <div className="screentime-weekly-section">
          <div className="screentime-weekly-header">
            <div>
              <h3>Weekly Distribution</h3>
              <p>Daily workload across Implementation, Compliance, Stakeholders, and Enablement</p>
            </div>
            <div className="screentime-week-picker">
              <button
                aria-label="Previous week"
                disabled={weekIndex === 0}
                onClick={() => setWeekIndex(0)}
              >
                <ChevronLeft size={15} />
              </button>
              <span>{week.label}</span>
              <button
                aria-label="Next week"
                disabled={weekIndex === 1}
                onClick={() => setWeekIndex(1)}
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>

          <div className="screentime-chart-wrapper">
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={week.data} barSize={26} margin={{ left: -22, right: 0, top: 10, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#F2E6EC" strokeDasharray="3 3" />
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#7A6E86', fontSize: 11, fontWeight: 600 }}
                  dy={6}
                />
                <YAxis
                  domain={[0, 12]}
                  ticks={[0, 3, 6, 9, 12]}
                  tickFormatter={v => `${v}h`}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#9C8EA8', fontSize: 10, fontWeight: 500 }}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  cursor={{ fill: 'rgba(244, 63, 94, 0.05)' }}
                  formatter={(v, name) => [
                    formatDuration(Number(v) * 60),
                    categories.find(c => c.id === name)?.name ?? name,
                  ]}
                />
                {categories.map((c, i) => (
                  <Bar
                    key={c.id}
                    dataKey={c.id}
                    stackId="time"
                    fill={c.color}
                    radius={i === categories.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 5. Most Used / Categories Breakdown (Apple Screen Time app list style) */}
        <div className="screentime-breakdown-section">
          <h3>Workload & Focus Allocation</h3>
          <div className="screentime-list">
            {categoriesToShow.map((cat, rank) => {
              const pct = Math.round((totalMinutes ? cat.minutes / totalMinutes : 0) * 100);
              return (
                <div key={cat.id} className="screentime-row">
                  <span className="screentime-row-rank">{rank + 1}</span>
                  <div className="screentime-row-icon" style={{ backgroundColor: `${cat.color}22` }}>
                    <span>{cat.icon}</span>
                  </div>
                  <div className="screentime-row-info">
                    <div className="screentime-row-top">
                      <strong>{cat.name}</strong>
                      <span className="screentime-row-duration">
                        {formatDuration(cat.minutes)} <small>({pct}%)</small>
                      </span>
                    </div>
                    {/* Progress Bar Track */}
                    <div className="screentime-track">
                      <div
                        className="screentime-fill"
                        style={{
                          width: `${pct}%`,
                          backgroundColor: cat.color,
                          boxShadow: `0 0 8px ${cat.color}88`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 6. Enterprise Workload & Capacity Insight */}
        <div className="screentime-vibe-card">
          <div className="vibe-sparkle">
            <Sparkles size={18} />
          </div>
          <div>
            <h4>{analytics ? 'Your schedule, in perspective' : 'Workload & Capacity Balance: Optimal ⚡'}</h4>
            <p>
              {analytics ? 'Your own timed Calendar events power these charts dynamically based on what you input. All-day events are excluded; uncategorized events appear under Admin & Operations. Tasks are separate from planned hours.' : 'Balanced time distribution dynamically categorized based on what you input across your work deliverables, meetings, operations, personal time, and learning.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
