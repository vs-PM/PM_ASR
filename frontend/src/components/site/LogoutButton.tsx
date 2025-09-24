'use client';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState } from 'react';

export default function LogoutButton() {
  const router = useRouter();
  const sp = useSearchParams();
  const [loading, setLoading] = useState(false);

  async function onLogout() {
    setLoading(true);
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
    } catch {
      // игнорируем — всё равно уходим со страницы
    } finally {
      // куда уходим: если был ?next=…, можно вернуть туда, иначе — на главную
      const next = sp?.get('next');
      const to = next && next.startsWith('/') ? next : '/';
      router.replace(to);
      router.refresh(); // обновит HeaderServer (сброшенное me)
    }
  }

  return (
    <button
      onClick={onLogout}
      disabled={loading}
      className="px-3 py-1 border rounded-md hover:bg-gray-50"
    >
      {loading ? 'Выходим…' : 'Выйти'}
    </button>
  );
}
