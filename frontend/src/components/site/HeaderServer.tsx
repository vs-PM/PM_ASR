// src/components/site/HeaderServer.tsx
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
import { cookies } from 'next/headers';
import { Header, type Me } from './Header';


async function buildCookieHeader(): Promise<string> {
  const jar = await cookies();
  const pairs = jar.getAll().map((c) => `${c.name}=${encodeURIComponent(c.value)}`);
  return pairs.join('; ');
}

type MePayload = NonNullable<Me>; // { user: { id:number; login:string; role:string } }

export default async function HeaderServer() {
  const cookieHeader = await buildCookieHeader();
  const base = process.env.AUTH_API_BASE || 'http://127.0.0.1:7000';

  let me: Me = null;
  try {
    const res = await fetch(`${base}/api/v1/auth/me`, {
      headers: { Cookie: cookieHeader },
      cache: 'no-store',
      next: { revalidate: 0 },
    });
    if (res.ok) {
      const json = (await res.json()) as MePayload; // { user: { ... } }
      me = json;
    }
  } catch {
    // ignore
  }

  return <Header me={me} />;
}
