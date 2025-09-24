import type { Metadata } from 'next';
import Providers from './providers';
import HeaderServer from '@/components/site/HeaderServer';
import './globals.css';


export const metadata: Metadata = { title: 'PM_ASR', description: 'Protocolizer UI' };


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-white text-black">
        <Providers>
          <HeaderServer />
          <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}