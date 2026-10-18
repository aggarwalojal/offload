import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Offload — Actionable Intelligence for Implementation Teams',
  description: 'Turn fragmented client conversations, meetings, and brain dumps into actionable calendar commitments, tasks, and real-time execution analytics.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
