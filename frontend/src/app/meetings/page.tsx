// src/app/meetings/page.tsx
'use client';

import * as React from 'react';
import Link from 'next/link';
import CreateMeetingDialog from '@/components/meetings/CreateMeetingDialog';
import { useMeetings, MEETINGS_PAGE_SIZE, useInvalidateMeetings } from '@/lib/meetings';
import { formatDate } from '@/lib/files';

export default function MeetingsPage() {
  const [page, setPage] = React.useState(1);
  const { data, isLoading, isError, error, isFetching } = useMeetings(page, MEETINGS_PAGE_SIZE);
  const invalidate = useInvalidateMeetings();

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const pages = Math.max(1, Math.ceil(total / MEETINGS_PAGE_SIZE));

  function go(delta: number) {
    setPage((p) => Math.min(pages, Math.max(1, p + delta)));
  }

  return (
    <main className="mx-auto max-w-6xl p-6 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Митинги</h1>
        <div className="flex items-center gap-2">
          <CreateMeetingDialog onCreated={() => invalidate(page)} />
          <span className="text-sm text-gray-500">{isFetching ? 'Обновляем…' : null}</span>
        </div>
      </header>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Список</h2>
          <div className="flex items-center gap-2">
            <button
              className="px-3 py-1 border rounded-md text-sm disabled:opacity-50"
              onClick={() => go(-1)}
              disabled={page <= 1}
            >
              ← Назад
            </button>
            <span className="text-sm">Стр. {page} / {pages}</span>
            <button
              className="px-3 py-1 border rounded-md text-sm disabled:opacity-50"
              onClick={() => go(1)}
              disabled={page >= pages}
            >
              Вперёд →
            </button>
          </div>
        </div>

        <div className="overflow-x-auto border rounded-lg">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-3 py-2">ID</th>
                <th className="text-left px-3 py-2">Название</th>
                <th className="text-left px-3 py-2">Файл</th>
                <th className="text-left px-3 py-2">Статус</th>
                <th className="text-left px-3 py-2">Создан</th>
                <th className="text-left px-3 py-2">Обновлён</th>
                <th className="text-left px-3 py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td className="px-3 py-4" colSpan={7}>Загружаем…</td></tr>
              ) : isError ? (
                <tr><td className="px-3 py-4 text-red-600" colSpan={7}>{(error as Error).message}</td></tr>
              ) : items.length === 0 ? (
                <tr><td className="px-3 py-4 text-gray-500" colSpan={7}>Пока пусто — создайте митинг</td></tr>
              ) : (
                items.map((t) => (
                  <tr key={t.id} className="border-t">
                    <td className="px-3 py-2 whitespace-nowrap">#{t.id}</td>
                    <td className="px-3 py-2">{t.title ?? '—'}</td>
                    <td className="px-3 py-2">{t.filename ?? '—'}</td>
                    <td className="px-3 py-2">{t.status ?? '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{t.created_at ? formatDate(t.created_at) : '—'}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{t.updated_at ? formatDate(t.updated_at) : '—'}</td>
                    <td className="px-3 py-2 space-x-2">
                      <Link href={`/meetings/${t.id}`} className="px-2 py-1 border rounded-md text-xs hover:bg-gray-100">
                        Открыть
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
