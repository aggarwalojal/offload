'use client';

import { useState } from 'react';
import { ArrowLeft, CheckCheck, MoreVertical, Phone, Send, Smile, Sparkles, Video } from 'lucide-react';
import { categories, sampleChats, type ChatMessage } from '@/lib/mock-data';

interface WhatsAppPhoneProps {
  onMessageSent?: (msg: string) => void;
  onSwitchToLive?: () => void;
}

const PRESET_CHIPS = [
  'Delta kickoff Thursday 2 PM',
  'Review Vantage HCM migration',
  'Q4 payroll filing due Friday',
  'Client sponsor sync Monday 10 AM',
];

export function WhatsAppPhone({ onMessageSent, onSwitchToLive }: WhatsAppPhoneProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(sampleChats);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  function handleSend(textToSend?: string) {
    const text = (textToSend || input).trim();
    if (!text) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      sender: 'user',
      text,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    if (onMessageSent) {
      onMessageSent(text);
    }

    // Simulate bot intelligent reply
    setTimeout(() => {
      let botText = "Offloaded! ✨ Synced to your schedule and commitment tracker! ⚡";

      const lower = text.toLowerCase();
      if (lower.includes('delta') || lower.includes('kickoff') || lower.includes('migration') || lower.includes('tenant')) {
        botText = "Offloaded! 💼 Synced to Client Implementation. Commitment locked in your project calendar!";
      } else if (lower.includes('payroll') || lower.includes('tax') || lower.includes('filing') || lower.includes('compliance')) {
        botText = "Offloaded! 📝 Added to Compliance & Payroll deliverables. Tracked and prioritized!";
      } else if (lower.includes('sponsor') || lower.includes('sync') || lower.includes('stakeholder') || lower.includes('debrief')) {
        botText = "Offloaded! 🤝 Scheduled with Stakeholder Sync. Alignment set!";
      } else if (lower.includes('training') || lower.includes('cert') || lower.includes('learn') || lower.includes('module')) {
        botText = "Offloaded! 📚 Added to Knowledge & Training. Continued implementation mastery!";
      } else if (lower.includes('focus') || lower.includes('reset') || lower.includes('wellness') || lower.includes('break')) {
        botText = "Offloaded! 🧘 Preserved as Focus & Wellness block. High-impact time protected!";
      }

      const botMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: 'bot',
        text: botText,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setIsTyping(false);
      setMessages(prev => [...prev, botMsg]);
    }, 700);
  }

  return (
    <div className="phone-mockup">
      {/* Phone Hardware Shell */}
      <div className="phone-speaker-notch">
        <span className="phone-clock">9:41</span>
        <div className="dynamic-island" />
        <span className="phone-signals">5G • 100%</span>
      </div>

      {/* WhatsApp Header */}
      <div className="wa-header">
        <button className="wa-back-btn" aria-label="Back">
          <ArrowLeft size={16} />
        </button>
        <div className="wa-avatar">
          <span>O</span>
          <i className="online-badge" />
        </div>
        <div className="wa-contact-info">
          <div className="wa-contact-name">
            <strong>Offload Bot</strong>
            <span className="verified-check">✓</span>
          </div>
          <small className="wa-status">online • WhatsApp Business</small>
        </div>
        <div className="wa-header-actions">
          <Video size={16} />
          <Phone size={15} />
          <MoreVertical size={16} />
        </div>
      </div>

      {/* WhatsApp Message Thread */}
      <div className="wa-body">
        <div className="wa-date-pill">TODAY</div>

        {messages.map(m => (
          <div key={m.id} className={`wa-bubble-wrapper ${m.sender}`}>
            <div className={`wa-bubble ${m.sender}`}>
              <p className="wa-bubble-text">{m.text}</p>
              {m.items && (
                <div className="wa-items-preview">
                  {m.items.map((item, idx) => {
                    const catObj = categories.find(c => c.id === item.category);
                    return (
                      <div key={idx} className="wa-item-row" style={{ borderLeftColor: catObj?.color }}>
                        <span className="wa-item-title">{item.title}</span>
                        <span className="wa-item-meta">{item.time}</span>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="wa-time-row">
                <span>{m.time}</span>
                {m.sender === 'user' && <CheckCheck size={13} className="wa-checks" />}
              </div>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="wa-bubble-wrapper bot">
            <div className="wa-bubble bot typing">
              <span>typing</span>
              <span className="dots">...</span>
            </div>
          </div>
        )}
      </div>

      {/* Quick Brain Dump Preset Chips */}
      <div className="wa-quick-chips">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', marginBottom: '4px', padding: '0 4px' }}>
          <span style={{ fontSize: '11px', color: '#64748B', fontWeight: 600 }}>Quick Brain Dumps</span>
          {onSwitchToLive && (
            <button
              type="button"
              onClick={onSwitchToLive}
              style={{
                background: 'none',
                border: 'none',
                fontSize: '11px',
                color: '#2563EB',
                fontWeight: 600,
                cursor: 'pointer',
                padding: 0
              }}
            >
              Connect Real Phone &rarr;
            </button>
          )}
        </div>
        {PRESET_CHIPS.map((chip, i) => (
          <button key={i} className="quick-chip" onClick={() => handleSend(chip)}>
            <Sparkles size={11} />
            {chip}
          </button>
        ))}
      </div>

      {/* Input Bar */}
      <div className="wa-footer">
        <button className="wa-emoji-btn" aria-label="Emoji">
          <Smile size={18} />
        </button>
        <input
          type="text"
          placeholder="Brain dump to offload..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
        />
        <button className="wa-send-btn" onClick={() => handleSend()} aria-label="Send">
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}
