import { Suspense } from 'react';
import Dashboard from '@/components/dashboard';

export default function Home() {
  return <Suspense fallback={<main className="workspace-loading">Loading your workspace…</main>}><Dashboard /></Suspense>;
}
