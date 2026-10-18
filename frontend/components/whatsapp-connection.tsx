'use client';

import { useEffect, useState } from 'react';
import { MessageCircle } from 'lucide-react';

export function WhatsAppConnection({ signedIn, googleConnected }: { signedIn: boolean; googleConnected: boolean }) {
  const [connected, setConnected] = useState(false);
  const [url, setUrl] = useState('');
  const [expiresAt, setExpiresAt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!signedIn) return;
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch('/api/whatsapp/link', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) return;
        const data = await response.json();
        if (!controller.signal.aborted) setConnected(data.connected === true);
      } catch { /* The explicit connect action presents an error if needed. */ }
    }
    void refresh();
    const timer = url && !connected ? setInterval(() => {
      if (Date.now() >= expiresAt) {
        setUrl(''); setError('Verification expired. Select Connect WhatsApp to try again.');
      } else void refresh();
    }, 3000) : undefined;
    return () => { controller.abort(); if (timer) clearInterval(timer); };
  }, [signedIn, url, expiresAt, connected]);

  async function connect() {
    setBusy(true); setError(''); setUrl('');
    try {
      const response = await fetch('/api/whatsapp/link', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not connect WhatsApp.');
      const link = new URL(data.url);
      if (link.origin !== 'https://wa.me') throw new Error('Could not create the verification message.');
      setUrl(link.href); setExpiresAt(Date.now() + data.expires_in * 1000);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Try again.'); }
    finally { setBusy(false); }
  }

  return <div>
    <div className="connection-row"><span className="feed-icon green"><MessageCircle size={19} /></span><div><h3>WhatsApp</h3><p>{signedIn && connected ? 'Send tasks from your linked WhatsApp account.' : 'Connect Google, then verify your WhatsApp number.'}</p></div><span className="subtle-pill">{signedIn && connected ? 'Connected' : 'Not connected'}</span></div>
    <div className="calendar-actions">
      {(!signedIn || !connected) && <button className="connect-google" disabled={!signedIn || !googleConnected || busy} onClick={() => void connect()}>{busy ? 'Preparing…' : 'Connect WhatsApp'}</button>}
      {signedIn && !connected && url && <p><a href={url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">Open WhatsApp and send verification</a><br />Use the phone you want to send tasks from. The message links it to your signed-in TimeSlice account. It expires in 15 minutes.</p>}
      {signedIn && connected && <p role="status">WhatsApp connected. Return to your chat and send a task.</p>}
      {!googleConnected && <p>Connect Google Calendar or Tasks below first.</p>}
      {error && <p className="connection-error" role="alert">{error}</p>}
    </div>
  </div>;
}
