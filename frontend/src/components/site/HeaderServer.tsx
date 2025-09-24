// src/components/site/HeaderServer.tsx
export const runtime = 'nodejs';         // важно: не edge
export const dynamic = 'force-dynamic';  // без статического кеша

import { cookies } from 'next/headers';
import { Header, type Me } from './Header';

function buildCookieHeader(): string {
  const jar = cookies();
  const pairs = jar.getAll().map(c => `${c.name}=${encodeURIComponent(c.value)}`);
  return pairs.join('; ');
}

export default async function HeaderServer() {
  const cookieHeader = buildCookieHeader();
  const base = process.env.AUTH_API_BASE || 'http://127.0.0.1:7000';

  let me: Me = null;
  try {
    const res = await fetch(`${base}/api/v1/auth/me`, {
      // Передаём куки вручную и полностью отключаем кеш
      headers: { Cookie: cookieHeader },
      cache: 'no-store',
      next: { revalidate: 0 },
    });
    if (res.ok) {
      const json = await res.json(); // { user: { id, login, role } }
      me = json as any; // тип Me выше
    }

  } catch {
    // ignore
  }

  return <Header me={me} />;
}
