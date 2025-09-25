// src/app/login/LoginForm.tsx
'use client';

import { useEffect, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { apiUrl } from '@/lib/api';

type Props = { nextPath: string };

export default function LoginForm({ nextPath }: Props) {
  const router = useRouter();
  const [u, setU] = useState('');
  const [p, setP] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    router.prefetch(nextPath);
  }, [nextPath, router]);

  async function doLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    if (!u || !p) {
      setErr('Заполните логин и пароль');
      return;
    }

    try {
      // важное: используем абсолютный API BASE, если он задан
      const loginUrl = apiUrl('/api/v1/auth/login');
      const res = await fetch(loginUrl, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ username: u.trim(), password: p }),
      });

      if (!res.ok) {
        let msg = res.status === 401 ? 'Неверный логин или пароль' : `${res.status} ${res.statusText}`;
        try {
          const ct = res.headers.get('content-type') ?? '';
          if (ct.includes('application/json')) {
            const j = (await res.json()) as { detail?: string; message?: string };
            msg = j.detail || j.message || msg;
          }
        } catch {}
        setErr(msg);
        return;
        }

      // Не вызываем относительный /auth/me (в проде он 404); достаточно refresh
      startTransition(() => {
        router.replace(nextPath);
        router.refresh(); // HeaderServer подтянет /auth/me сервером
      });
    } catch {
      setErr('Сеть недоступна. Проверьте подключение.');
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Вход</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={doLogin} noValidate>
          <div>
            <label htmlFor="login" className="text-sm">Логин</label>
            <Input id="login" name="login" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required />
          </div>
          <div>
            <label htmlFor="password" className="text-sm">Пароль</label>
            <Input id="password" name="password" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required />
          </div>
          {err && <p className="text-sm text-red-600">{err}</p>}
          <button
            type="submit"
            disabled={isPending}
            className="w-full inline-flex items-center justify-center rounded-md border px-3 py-2 text-sm font-medium hover:bg-gray-100 disabled:opacity-60"
            aria-busy={isPending}
          >
            {isPending ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </CardContent>
    </Card>
  );
}
