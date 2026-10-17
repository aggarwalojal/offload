'use client';

import { useCallback, useEffect, useState } from 'react';
import { calendarRange, normalizeEvents, type GoogleEvent } from './calendar-data';
import type { Activity } from './mock-data';

export type CalendarConnection = {
  configured: boolean; signed_in: boolean; connected: boolean; email?: string | null;
};

export function useCalendar() {
  const [connection, setConnection] = useState<CalendarConnection>({ configured: false, signed_in: false, connected: false });
  const [items, setItems] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [allDayCount, setAllDayCount] = useState(0);
  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/google/connection', { cache: 'no-store' });
      const status = await response.json();
      setLoading(true); setError('');
      setConnection({ configured: !!status.configured, signed_in: !!status.signed_in, connected: !!status.connected, email: status.email });
      if (!response.ok) { setItems([]); throw new Error(status.detail || 'Calendar connection could not be checked.'); }
      setItems([]);
      if (status.connected) {
        const eventsResponse = await fetch(`/api/google/events?${new URLSearchParams(calendarRange())}`, { cache: 'no-store' });
        const data = await eventsResponse.json();
        if (!eventsResponse.ok) throw new Error(data.detail || 'Calendar could not be loaded.');
        const events: GoogleEvent[] = data.events;
        if (!Array.isArray(events)) throw new Error('Calendar returned an invalid response.');
        setItems(normalizeEvents(events));
        setAllDayCount(events.filter(e => e.start.date).length);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Calendar is unavailable.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  return { connection, items, loading, error, allDayCount, refresh };
}
