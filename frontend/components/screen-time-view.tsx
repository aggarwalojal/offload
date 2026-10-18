'use client';

import type { liveAnalytics } from '@/lib/calendar-data';
import { useState } from 'react';
import { ChevronLeft, ChevronRight, Clock, Sparkles, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { categories, distribution as demoDistribution, formatDuration, weeks as demoWeeks, type Category } from '@/lib/mock-data';

const tooltipStyle = {
  background: '#FFFFFF',
  border: '1px solid #F2E6EC',
  borderRadius: 14,
  color: '#191122',
  fontSize: 12,
  fontWeight: 600,
  boxShadow: '0 10px 25px -5px rgba(244, 63, 94, 0.15), 0 2px 6px rgba(0, 0, 0, 0.04)',
};

export function ScreenTimeView({ analytics }: { analytics?: ReturnType<typeof liveAnalytics> }) {
  const distribution = analytics?.distribution ?? demoDistribution;
  const weeks = analytics?.weeks ?? demoWeeks;
  const totalMinutes = distribution.reduce((sum, item) => sum + item.minutes, 0);
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null);
  const [weekIndex, setWeekIndex] = useState(1);
  const week = weeks[weekIndex];

  // Sort categories by time spent descending (Apple Screen Time "Most Used" pattern)
  const rankedCategories = [...distribution].sort((a, b) => b.minutes - a.minutes);

  return (
    <div className="screentime-container">
      {/* 1. Main Daily Screen Time Card */}
      <div className="screentime-card">
        <div className="screentime-header">
          <div className="screentime-icon-wrapper">
            <Clock size={20} className="text-pink-400" />
          </div>
          <div>
            <span className="screentime-caption">TODAY’S OFFLOAD ENERGY</span>
            <div className="screentime-hero-stat">
              <h1>{formatDuration(totalMinutes)}</h1>
              <span className="screentime-trend-pill">
                <TrendingUp size={13} />
                {analytics ? 'Calendar time' : '+14% from avg'}
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
              <p>Daily hours across Academics, Career, Social, Health, and Admin</p>
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
          <h3>Energy Breakdown</h3>
          <div className="screentime-list">
            {rankedCategories.map((cat, rank) => {
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

        {/* 6. Vibe Check / Balance Insight */}
        <div className="screentime-vibe-card">
          <div className="vibe-sparkle">
            <Sparkles size={18} />
          </div>
          <div>
            <h4>{analytics ? 'Your time, in perspective' : 'Vibe Check: Balanced Flow 🌸'}</h4>
            <p>
              {analytics ? 'Your own timed Calendar events power these charts. All-day events are excluded; uncategorized events appear under Admin. Tasks are separate from planned hours.' : 'Sample time distribution for a balanced day of work, friends, and health.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
