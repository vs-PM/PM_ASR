import Link from 'next/link';
import { cookies } from 'next/headers';
import Landing from '@/components/Landing';

export default async function Page() {
  const jar = cookies();
  const cookieHeader = jar.toString();
  const base = process.env.AUTH_API_BASE || 'http://127.0.0.1:7000';

  let me: { id: number; username: string } | null = null;
  try {
    const res = await fetch(`${base}/api/v1/auth/me`, {
      headers: { cookie: cookieHeader },
      cache: 'no-store',
    });
    if (res.ok) me = (await res.json()) as { id: number; username: string };
  } catch {
    /* ignore */
  }

  if (!me) {
    return <Landing />;
  }

  // Авторизован — короткий “dashboard” с быстрыми ссылками
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Протоколизатор</h1>
      <p className="text-sm text-gray-600">Добро пожаловать, {me.username}!</p>
      <ul className="list-disc pl-6 text-sm space-y-1">
        <li>
          <Link className="underline" href="/audio">Перейти к аудиофайлам</Link>
        </li>
        <li>
          <Link className="underline" href="/meetings">Открыть митинги</Link>
        </li>
      </ul>
    </section>
  );
}
