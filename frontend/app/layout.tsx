import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'TimeSlice — Your time, in perspective',
  description: 'A little more intentional, every day. Your WhatsApp-powered productivity companion and planned-time dashboard.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
