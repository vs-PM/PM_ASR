'use client';

import * as React from 'react';
import UploadDrop from '@/components/upload/UploadDrop';
import { PAGE_SIZE, useFiles, useInvalidateFiles, formatBytes, formatDate } from '@/lib/files';
import { audioUrlById } from '@/lib/files';

export default function AudioPage() {
  const [page, setPage] = React.useState(1);
  const [playId, setPlayId] = React.useState<number | null>(null);
  const { data, isLoading, isFetching, isError, error } = useFiles(page, PAGE_SIZE);
  const invalidate = useInvalidateFiles();

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function go(delta: number) {
    setPage(p => Math.min(pages, Math.max(1, p + delta)));
  }

  // если страница поменялась, сбросим выбранный трек
  React.useEffect(() => { setPlayId(null); }, [page]);

  return (
    <main className="mx-auto max-w-5xl p-6 space-y-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Аудиофайлы</h1>
        <div className="text-sm text-gray-500">{isFetching ? 'Обновляем…' : null}</div>
      </header>

      {/* Drag&Drop */}
      <UploadDrop onAnyFinished={() => invalidate(page)} />

      {/* Таблица со списком */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Последние загрузки</h2>
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
                <th className="text-left px-3 py-2">Имя</th>
                <th className="text-left px-3 py-2">Размер</th>
                <th className="text-left px-3 py-2">Тип</th>
                <th className="text-left px-3 py-2">Загружен</th>
                <th className="text-left px-3 py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td className="px-3 py-4" colSpan={5}>Загружаем…</td></tr>
              ) : isError ? (
                <tr><td className="px-3 py-4 text-red-600" colSpan={5}>
                  {(error as Error)?.message || 'Ошибка загрузки списка'}
                </td></tr>
              ) : items.length === 0 ? (
                <tr><td className="px-3 py-4 text-gray-500" colSpan={5}>Список пуст</td></tr>
              ) : (
                items.map(f => {
                  const isActive = playId === f.id;
                  return (
                    <tr key={f.id} className="border-t align-top">
                      <td className="px-3 py-2">{f.filename}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{formatBytes(f.size_bytes)}</td>
                      <td className="px-3 py-2">{f.mimetype || '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{formatDate(f.created_at)}</td>
                      <td className="px-3 py-2">
                        <button
                          className="px-2 py-1 border rounded-md text-xs hover:bg-gray-100"
                          onClick={() => setPlayId(isActive ? null : f.id)}
                          aria-pressed={isActive}
                        >
                          {isActive ? 'Скрыть' : 'Слушать'}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Плеер для выбранного файла */}
        {playId != null && (
          <div className="mt-4 border rounded-lg p-3">
            <p className="text-sm text-gray-600 mb-2">
              Воспроизведение: <span className="font-medium">
                {items.find(x => x.id === playId)?.filename || `#${playId}`}
              </span>
            </p>
            <audio
              key={playId}
              controls
              preload="none"
              className="w-full"
              // важное: другого домена → куки и CORS
              crossOrigin="use-credentials"
              src={audioUrlById(playId)}
            />
          </div>
        )}
      </section>
    </main>
  );
}
