export type Category = 'academics' | 'career' | 'social' | 'health' | 'admin';
export type View = 'Dashboard' | 'Activity' | 'Settings';

export const categories: { id: Category; name: string; color: string; icon: string }[] = [
  { id: 'academics', name: 'Academics', color: '#B388FF', icon: '📚' },
  { id: 'career', name: 'Career', color: '#FF758C', icon: '💼' },
  { id: 'social', name: 'Social', color: '#FF4081', icon: '🎉' },
  { id: 'health', name: 'Health', color: '#00E676', icon: '🏃' },
  { id: 'admin', name: 'Admin', color: '#00E5FF', icon: '📝' },
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
  { id: 'a1', title: 'Deep work · Machine learning', category: 'academics', start_time: '2026-10-17T09:00:00-04:00', end_time: '2026-10-17T11:00:00-04:00', source: 'whatsapp', phase: 'completed' },
  { id: 'a2', title: 'Product design internship prep', category: 'career', start_time: '2026-10-17T11:30:00-04:00', end_time: '2026-10-17T13:00:00-04:00', source: 'whatsapp', phase: 'completed' },
  { id: 'a3', title: 'Lunch with Sarah & Alex', category: 'social', start_time: '2026-10-17T13:00:00-04:00', end_time: '2026-10-17T14:00:00-04:00', source: 'calendar', phase: 'completed' },
  { id: 'a4', title: 'Afternoon gym session', category: 'health', start_time: '2026-10-17T16:00:00-04:00', end_time: '2026-10-17T17:00:00-04:00', source: 'whatsapp', phase: 'upcoming' },
  { id: 'a5', title: 'CS 1331 Java Project', category: 'academics', start_time: '2026-10-17T19:00:00-04:00', end_time: '2026-10-17T21:00:00-04:00', source: 'whatsapp', phase: 'upcoming' },
  { id: 'a6', title: 'Catch up with Mom', category: 'social', start_time: '2026-10-17T21:00:00-04:00', end_time: '2026-10-17T21:30:00-04:00', source: 'whatsapp', phase: 'upcoming' },
  { id: 'a7', title: 'Inbox & weekly planning', category: 'admin', start_time: '2026-10-17T21:30:00-04:00', end_time: '2026-10-17T22:00:00-04:00', source: 'whatsapp', phase: 'upcoming' },
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
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }).format(new Date(iso));
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
    text: 'I need to study Java for two hours tonight, apply to an internship tomorrow, and go to my club meeting Friday at 7 PM.',
    time: '4:47 PM',
  },
  {
    id: 'c2',
    sender: 'bot',
    text: "Offloaded! ✨ Synced 'Study Java' (2 hrs) to Academics, 'Apply to internship' to Career Tasks, and 'Club meeting' to Social. Your Academics energy just increased by 2 hours! 🌸",
    time: '4:47 PM',
    items: [
      { title: 'Study Java', category: 'academics', time: 'Tonight, 7:00 – 9:00 PM' },
      { title: 'Apply to internship', category: 'career', time: 'Due tomorrow' },
      { title: 'Club meeting', category: 'social', time: 'Friday, 7:00 – 8:00 PM' },
    ],
  },
];
