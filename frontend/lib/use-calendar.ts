'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { calendarRange, normalizeEvents, type GoogleEvent } from './calendar-data';
import type { Activity } from './mock-data';

export type GoogleTask = { external_id: string; title: string; due?: string | null; status: string };
export type CalendarConnection = {
  display_name?: string | null; tasks_connected?: boolean; tasks_enabled?: boolean; configured: boolean; signed_in: boolean; connected: boolean; email?: string | null;
};

export function useCalendar() {
  const [connection, setConnection] = useState<CalendarConnection>({ configured: false, signed_in: false, connected: false });
  const [items, setItems] = useState<Activity[]>([]);
  const [tasks, setTasks] = useState<GoogleTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState('');
  const [allDayCount, setAllDayCount] = useState(0);
  const pending = useRef(false);
  const refresh = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    setRefreshing(true);
    try {
      const response = await fetch('/api/google/connection', { cache: 'no-store' });
      const status = await response.json();
      if (!response.ok) throw new Error(status.detail || 'Google connections could not be checked.');
      setConnection({ configured: !!status.configured, signed_in: !!status.signed_in, connected: !!status.connected,
        email: status.email, display_name: status.display_name, tasks_connected: !!status.tasks_connected, tasks_enabled: !!status.tasks_enabled });
      if (!status.connected) { setItems([]); setAllDayCount(0); }
      if (!status.tasks_connected) setTasks([]);
      const failures: string[] = [];
      await Promise.all([
        (async () => {
          if (!status.connected) return;
          try {
            const result = await fetch(`/api/google/events?${new URLSearchParams(calendarRange())}`, { cache: 'no-store' });
            const data = await result.json();
            if (!result.ok || !Array.isArray(data.events)) throw new Error(data.detail || 'Calendar could not be loaded.');
            const events: GoogleEvent[] = data.events;
            setItems(normalizeEvents(events)); setAllDayCount(events.filter(e => e.start.date).length);
          } catch (cause) { failures.push(cause instanceof Error ? cause.message : 'Calendar is unavailable.'); }
        })(),
        (async () => {
          if (!status.tasks_connected) return;
          try {
            const result = await fetch('/api/google/tasks', { cache: 'no-store' });
            const data = await result.json();
            if (!result.ok || !Array.isArray(data.tasks)) throw new Error(data.detail || 'Tasks could not be loaded.');
            setTasks(data.tasks);
          } catch (cause) { failures.push(cause instanceof Error ? cause.message : 'Tasks are unavailable.'); }
        })(),
      ]);
      setError(failures.join(' '));
      if (!failures.length) setLastUpdated(new Date());
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Google is unavailable.'); }
    finally { setLoading(false); setRefreshing(false); pending.current = false; }
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void refresh(); });
    const update = () => { if (document.visibilityState === 'visible') void refresh(); };
    const timer = setInterval(update, 15000);
    window.addEventListener('focus', update);
    window.addEventListener('online', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      active = false; clearInterval(timer);
      window.removeEventListener('focus', update); window.removeEventListener('online', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [refresh]);
  return { connection, items, tasks, loading, refreshing, lastUpdated, error, allDayCount, refresh };
}
