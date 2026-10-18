import { categories, type Activity, type Category, type WeekDay } from './mock-data';

export type GoogleEvent = {
  external_id: string;
  title: string;
  start: { dateTime?: string; date?: string };
  end: { dateTime?: string; date?: string };
  category: string | null;
  status?: string;
  transparency?: string;
};

export function normalizeEvents(events: GoogleEvent[], now = Date.now()): Activity[] {
  return events.filter(e => e.status !== 'cancelled' && e.transparency !== 'transparent' && e.start.dateTime && e.end.dateTime)
    .filter(e => Number.isFinite(Date.parse(e.start.dateTime!)) && Date.parse(e.end.dateTime!) > Date.parse(e.start.dateTime!))
    .map(e => ({ id: e.external_id, title: e.title || 'Untitled event',
      category: categories.some(c => c.id === e.category) ? e.category as Category : 'admin',
      start_time: e.start.dateTime!, end_time: e.end.dateTime!, source: 'calendar' as const,
      phase: Date.parse(e.end.dateTime!) <= now ? 'completed' as const : 'upcoming' as const,
    })).sort((a, b) => Date.parse(a.start_time) - Date.parse(b.start_time));
}

// Count the union of planned intervals, splitting overlapping slices evenly
// across active categories. An overlapping hour never becomes two planned hours.
export function categoryMinutes(items: Activity[], start: Date, end: Date) {
  const result = Object.fromEntries(categories.map(c => [c.id, 0])) as Record<Category, number>;
  const intervals = items.map(item => ({ category: item.category,
    start: Math.max(+start, Date.parse(item.start_time)), end: Math.min(+end, Date.parse(item.end_time)),
  })).filter(item => item.end > item.start);
  const boundaries = [...new Set(intervals.flatMap(item => [item.start, item.end]))].sort((a, b) => a - b);
  for (let i = 0; i < boundaries.length - 1; i++) {
    const active = [...new Set(intervals.filter(item => item.start <= boundaries[i] && item.end > boundaries[i]).map(item => item.category))];
    const minutes = (boundaries[i + 1] - boundaries[i]) / 60000;
    for (const category of active) result[category] += minutes / active.length;
  }
  return result;
}

export function liveAnalytics(items: Activity[], now = new Date()) {
  const today = new Date(now); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const totals = categoryMinutes(items, today, tomorrow);
  const distribution = categories.map(c => ({ ...c, minutes: totals[c.id] }));
  const monday = new Date(today); monday.setDate(today.getDate() - (today.getDay() + 6) % 7);
  const weeks = [-1, 0, 1].map(offset => {
    const first = new Date(monday); first.setDate(monday.getDate() + offset * 7);
    const data: WeekDay[] = Array.from({ length: 7 }, (_, i) => {
      const start = new Date(first); start.setDate(first.getDate() + i);
      const end = new Date(start); end.setDate(start.getDate() + 1);
      const amounts = categoryMinutes(items, start, end);
      return { day: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][i],
        ...Object.fromEntries(categories.map(c => [c.id, amounts[c.id] / 60])) } as WeekDay;
    });
    const last = new Date(first); last.setDate(first.getDate() + 6);
    const label = `${first.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${last.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
    return { label, data };
  });
  return { distribution, weeks, todayItems: items.filter(item => Date.parse(item.start_time) < +tomorrow && Date.parse(item.end_time) > +today),
    date: today.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }) };
}

export function calendarRange(now = new Date()) {
  const start = new Date(now); start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - (start.getDay() + 6) % 7 - 7);
  const end = new Date(start); end.setDate(start.getDate() + 21);
  return { start_time: start.toISOString(), end_time: end.toISOString() };
}
