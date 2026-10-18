'use client';
import { useState } from 'react';

export function ProfileName({ name, onSaved }: { name?: string | null; onSaved: () => Promise<void> }) {
  const [value, setValue] = useState(name ?? '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  return <section className="profile-name-card"><h2>{name ? `Hey, ${name}!` : 'Hey! What should Offload call you?'}</h2><p>Tell us your preferred name for your dashboard and WhatsApp greetings.</p><form onSubmit={async event => {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const response = await fetch('/api/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: value }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not save your name.');
      await onSaved(); setMessage('Name saved. Offload will remember you.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Please try again.'); }
    finally { setBusy(false); }
  }}><label htmlFor="offload-preferred-name">Your name</label><div><input id="offload-preferred-name" autoComplete="given-name" required maxLength={60} value={value} onChange={event => setValue(event.target.value)} placeholder="e.g. Ojal" /><button type="submit" className="connect-google" disabled={busy}>{busy ? 'Saving…' : 'Save name'}</button></div></form>{message && <p role="status">{message}</p>}</section>;
}
