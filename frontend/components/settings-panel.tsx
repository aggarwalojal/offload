'use client';

import { useState } from 'react';
import { CalendarDays, MessageCircle, ShieldCheck, Sparkles } from 'lucide-react';
import { Panel } from './ui';

export function SettingsPanel() {
  const [digest, setDigest] = useState(true);
  const [recap, setRecap] = useState(true);
  return (
    <div className="settings-grid">
      <Panel className="preferences-panel"><div className="panel-heading"><div><h2>Your day, your way</h2><p>Preferences for a little less planning.</p></div><Sparkles size={18} /></div>
        <div className="settings-content">{[
          { title: 'Morning briefing', description: 'A simple look at what’s ahead, at 8:00 AM.', checked: digest, set: setDigest },
          { title: 'Evening recap', description: 'A moment to reflect on your day, at 9:00 PM.', checked: recap, set: setRecap },
        ].map(item => <div className="setting-row" key={item.title}><div><h3>{item.title}</h3><p>{item.description}</p></div><button role="switch" aria-checked={item.checked} aria-label={item.title} className={`toggle ${item.checked ? 'on' : ''}`} onClick={() => item.set(!item.checked)}><span /></button></div>)}
        <div className="setting-row"><div><h3>Timezone</h3><p>Used to display your demo schedule.</p></div><span className="timezone">Eastern Time (ET)</span></div>
        <p className="settings-note">Demo preferences last until you reload this page. No messages are scheduled.</p></div>
      </Panel>
      <Panel className="connections-panel"><div className="panel-heading"><div><h2>Your connected world</h2><p>One conversation. A more organized day.</p></div></div><div className="settings-content">{[
        { name: 'WhatsApp', icon: MessageCircle, description: 'Turn your messages into plans.', color: 'green' },
        { name: 'Google Calendar', icon: CalendarDays, description: 'Give every plan a place.', color: 'blue' },
      ].map(item => <div className="connection-row" key={item.name}><span className={`feed-icon ${item.color}`}><item.icon size={19} /></span><div><h3>{item.name}</h3><p>{item.description}</p></div><span className="subtle-pill">Demo</span></div>)}
      <div className="privacy-note"><ShieldCheck size={18} /><p>This workspace uses sample data. Your real WhatsApp and Google accounts are not connected.</p></div></div></Panel>
    </div>
  );
}
