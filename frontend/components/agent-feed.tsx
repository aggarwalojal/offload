'use client';

import { useEffect, useState } from 'react';
import { CalendarDays, Check, CheckCheck, Clock3, MessageCircle, Pause, Play, ShieldCheck, Sparkles } from 'lucide-react';
import type { Category } from '@/lib/mock-data';
import { CategoryBadge, Panel } from './ui';

const examples: { message: string; title: string; category: Category; time: string }[] = [
  { message: 'Delta kickoff workshop tomorrow from 2 to 4 PM', title: 'Delta · Client Kickoff Workshop', category: 'career', time: 'Tomorrow, 2:00 – 4:00 PM' },
  { message: 'Review Vantage HCM tenant migration checklist by Thursday', title: 'Vantage HCM Migration Review', category: 'admin', time: 'Thursday, 10:00 – 11:30 AM' },
  { message: 'Executive sponsor alignment call Friday from 1 to 2 PM', title: 'Executive Sponsor Alignment', category: 'social', time: 'Friday, 1:00 – 2:00 PM' },
];

export function AgentFeed() {
  const [exampleIndex, setExampleIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setExampleIndex(i => (i + 1) % examples.length), 8000);
    return () => clearInterval(id);
  }, [playing]);
  const example = examples[exampleIndex];
  return (
    <Panel className="agent-panel">
      <div className="panel-heading"><div className="agent-heading"><Sparkles size={18} /><h2>Your AI, at work</h2></div><span className={`live-badge ${playing ? '' : 'paused'}`}><i />{playing ? 'LIVE DEMO' : 'PAUSED'}</span></div>
      <p className="agent-description">You send a message. We take it from there.</p>
      <div className="feed" key={exampleIndex}>
        <div className="feed-item"><span className="feed-icon green"><MessageCircle size={16} /></span><div><div className="feed-label">Message received <time>Just now</time></div><div className="message-bubble">“{example.message}”<CheckCheck size={13} /></div><small>From your WhatsApp</small></div></div>
        <div className="feed-item"><span className="feed-icon purple"><Sparkles size={16} /></span><div><div className="feed-label">Intent understood <time>Just now</time></div><p>One clear plan, with a time and a place<br className="desktop-break" /> in your day.</p><CategoryBadge category={example.category} /></div></div>
        <div className="feed-item"><span className="feed-icon blue"><CalendarDays size={16} /></span><div><div className="feed-label">Calendar event created <time>Just now</time></div><p>{example.title}</p><span className="event-time"><Clock3 size={11} />{example.time}</span></div></div>
        <div className="feed-item last"><span className="feed-icon green"><Check size={16} /></span><div><div className="feed-label">All set. You’re in control.</div><p>Confirmation sent to WhatsApp <CheckCheck size={12} /></p></div></div>
      </div>
      <div className="feed-footer"><ShieldCheck size={13} /><span>Simulated activity · No APIs connected</span><button aria-label={playing ? 'Pause simulated feed' : 'Resume simulated feed'} onClick={() => setPlaying(p => !p)}>{playing ? <Pause size={12} /> : <Play size={12} />}</button></div>
    </Panel>
  );
}
