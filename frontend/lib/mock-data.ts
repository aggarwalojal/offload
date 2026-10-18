export type Category = 'academics' | 'career' | 'social' | 'health' | 'admin';
export type View = 'Dashboard' | 'Activity' | 'Settings';

export const categories: { id: Category; name: string; color: string; icon: string }[] = [
  { id: 'academics', name: 'Knowledge & Training', color: '#8B5CF6', icon: '📚' },
  { id: 'career', name: 'Client Implementation', color: '#F43F5E', icon: '💼' },
  { id: 'social', name: 'Stakeholder Sync', color: '#EC4899', icon: '🤝' },
  { id: 'health', name: 'Focus & Wellness', color: '#10B981', icon: '🏃' },
  { id: 'admin', name: 'Compliance & Payroll', color: '#0284C7', icon: '📝' },
];

export type Activity = {
  id: string;
  title: string;
  category: Category;
  start_time: string;
  end_time: string;
  source: 'whatsapp' | 'calendar';
  phase: 'completed' | 'upcoming';
};

export const demoDate = 'Saturday, October 17, 2026';

export const initialActivities: Activity[] = [
  { id: 'a1', title: 'Delta Airlines · Kickoff sync', category: 'career', start_time: '2026-10-17T09:00:00-04:00', end_time: '2026-10-17T10:30:00-04:00', source: 'whatsapp', phase: 'completed' },
  { id: 'a2', title: 'Vantage HCM migration architecture review', category: 'career', start_time: '2026-10-17T11:00:00-04:00', end_time: '2026-10-17T12:30:00-04:00', source: 'whatsapp', phase: 'completed' },
  { id: 'a3', title: 'Lunch & debrief with implementation team', category: 'social', start_time: '2026-10-17T13:00:00-04:00', end_time: '2026-10-17T14:00:00-04:00', source: 'calendar', phase: 'completed' },
  { id: 'a4', title: 'Focus block · Payroll tax compliance validation', category: 'admin', start_time: '2026-10-17T14:30:00-04:00', end_time: '2026-10-17T16:00:00-04:00', source: 'whatsapp', phase: 'upcoming' },
  { id: 'a5', title: 'ADP client training module walkthrough', category: 'academics', start_time: '2026-10-17T16:30:00-04:00', end_time: '2026-10-17T17:30:00-04:00', source: 'whatsapp', phase: 'upcoming' },
  { id: 'a6', title: 'Evening wellness break & reset', category: 'health', start_time: '2026-10-17T18:00:00-04:00', end_time: '2026-10-17T19:00:00-04:00', source: 'whatsapp', phase: 'upcoming' },
  { id: 'a7', title: 'Review open tenant action items & risks', category: 'admin', start_time: '2026-10-17T19:30:00-04:00', end_time: '2026-10-17T20:00:00-04:00', source: 'whatsapp', phase: 'upcoming' },
];

export const activities = initialActivities;

export function durationMinutes(activity: Activity) {
  return (Date.parse(activity.end_time) - Date.parse(activity.start_time)) / 60000;
}

export function formatDuration(minutes: number) {
  const rounded = Math.round(minutes);
  const hours = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return [hours ? `${hours}h` : '', remainder ? `${remainder}m` : ''].filter(Boolean).join(' ') || '0m';
}

export function timeLabel(iso: string) {
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
}

export const distribution = categories.map(category => ({
  ...category,
  minutes: activities.filter(a => a.category === category.id).reduce((sum, a) => sum + durationMinutes(a), 0),
}));

export const totalMinutes = distribution.reduce((sum, c) => sum + c.minutes, 0);
export const busiestCategory = [...distribution].sort((a, b) => b.minutes - a.minutes)[0];

export type WeekDay = { day: string } & Record<Category, number>;
const thisWeek: WeekDay[] = [
  { day: 'Mon', academics: 3, career: 2, social: 1, health: 1, admin: 0.5 },
  { day: 'Tue', academics: 4, career: 2.5, social: 1, health: 0.5, admin: 1 },
  { day: 'Wed', academics: 2.5, career: 3, social: 1.5, health: 1, admin: 0.5 },
  { day: 'Thu', academics: 1.5, career: 1, social: 2.5, health: 1.5, admin: 0.5 },
  { day: 'Fri', academics: 3, career: 2, social: 2, health: 1, admin: 0.5 },
  { day: 'Sat', academics: 4, career: 2.5, social: 1.5, health: 1, admin: 0.5 },
  { day: 'Sun', academics: 2, career: 0.5, social: 1.5, health: 1, admin: 1 },
];

const previousWeek: WeekDay[] = thisWeek.map(day => ({
  day: day.day,
  academics: day.academics * 0.9,
  career: day.career * 0.9,
  social: day.social * 0.9,
  health: day.health * 0.9,
  admin: day.admin * 0.9,
}));

export const weeks = [
  { label: 'Oct 5 – 11', data: previousWeek },
  { label: 'Oct 12 – 18', data: thisWeek },
];

export type ChatMessage = {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  time: string;
  items?: { title: string; category: Category; time: string }[];
};

export const sampleChats: ChatMessage[] = [
  {
    id: 'c1',
    sender: 'user',
    text: 'Client kick-off meeting with Delta tomorrow from 2 to 3 PM, finish the Q4 payroll filing checklist by Thursday, and review Vantage HCM migration risks.',
    time: '4:47 PM',
  },
  {
    id: 'c2',
    sender: 'bot',
    text: "Offloaded! ✨ Synced 'Client kick-off meeting with Delta' (2–3 PM) to Client Implementation, 'Q4 payroll filing checklist' to Compliance Tasks, and 'Review Vantage HCM migration risks' to Project Deliverables. Your schedule and commitments are locked in! ⚡",
    time: '4:47 PM',
    items: [
      { title: 'Client kick-off meeting with Delta', category: 'career', time: 'Tomorrow, 2:00 – 3:00 PM' },
      { title: 'Q4 payroll filing checklist', category: 'admin', time: 'Due Thursday' },
      { title: 'Review Vantage HCM migration risks', category: 'career', time: 'Action item' },
    ],
  },
];
