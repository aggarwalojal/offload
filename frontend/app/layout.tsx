import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'offload. — Screen Time for your real life',
  description: 'Brain dump your chaotic thoughts on WhatsApp. We turn them into calendar blocks and visual Screen Time analytics.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
