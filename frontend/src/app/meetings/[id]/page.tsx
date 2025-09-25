// src/app/meetings/[id]/page.tsx
'use client';

import * as React from 'react';
import { useParams } from 'next/navigation';
import { Segmentation, useMeeting, useRunTranscription } from '@/lib/meetings';
import { formatDate } from '@/lib/files';

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data, isLoading, isError, error } = useMeeting(id);
  const run = useRunTranscription();

  const [seg, setSeg] = React.useState<Segmentation>('vad');

  const busy = run.isPending || (data?.status === 'processing' || data?.status === 'transcription_processing');

  function renderResult() {
    if (!data) return null;

    // 1) Явный текст
    if (data.text) {
      return <pre className="whitespace-pre-wrap text-sm">{data.text}</pre>;
    }
    if (data.result && typeof data.result.text === 'string') {
      return <pre className="whitespace-pre-wrap text-sm">{data.result.text}</pre>;
    }
    // 2) Сегменты → склеим
    if (Array.isArray(data.segments) && data.segments.length) {
      return (
        <div className="space-y-2 text-sm">
          {data.segments.map((s, i) => (
            <p key={i}><span className="text-gray-500">{s.start.toFixed?.(1) ?? s.start}–{s.end.toFixed?.(1) ?? s.end}s:</span> {s.text}</p>
          ))}
        </div>
      );
    }
    // 3) Ничего явного → покажем сырой JSON
    return (
      <pre className="text-xs overflow-auto">{JSON.stringify(data, null, 2)}</pre>
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Митинг #{id}</h1>
        {data && (
          <p className="text-sm text-gray-600">
            {data.title ? <>«{data.title}» · </> : null}
            Файл: {data.filename ?? (data.file_id ? `#${data.file_id}` : '—')} ·
            Статус: <span className="font-medium">{data.status ?? '—'}</span> ·
            Создан: {data.created_at ? formatDate(data.created_at) : '—'} ·
            Обновлён: {data.updated_at ? formatDate(data.updated_at) : '—'}
          </p>
        )}
      </header>

      {isLoading ? (
        <p>Загружаем…</p>
      ) : isError ? (
        <p className="text-red-600">{(error as Error).message}</p>
      ) : !data ? (
        <p>Не найдено</p>
      ) : (
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Левая колонка — управление */}
          <div className="lg:col-span-1 space-y-4">
            <div className="border rounded-lg p-4">
              <h2 className="font-medium mb-2">Деление аудио</h2>
              <div className="space-y-1 text-sm">
                <label className="flex items-center gap-2">
                  <input type="radio" name="seg" value="none" checked={seg==='none'} onChange={() => setSeg('none')} />
                  Без деления
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="seg" value="vad" checked={seg==='vad'} onChange={() => setSeg('vad')} />
                  VAD (по паузам)
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="seg" value="speaker" checked={seg==='speaker'} onChange={() => setSeg('speaker')} />
                  Диаризация (по спикерам)
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="seg" value="fixed_30s" checked={seg==='fixed_30s'} onChange={() => setSeg('fixed_30s')} />
                  Фиксированные 30с
                </label>
              </div>

              <button
                className="mt-3 w-full px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
                disabled={busy}
                onClick={() => run.mutate({ id, seg })}
              >
                {busy ? 'Обрабатываем…' : 'Запустить транскрипцию'}
              </button>

              {data.error && <p className="mt-2 text-sm text-red-600">Ошибка: {data.error}</p>}
            </div>
          </div>

          {/* Правая часть — результат */}
          <div className="lg:col-span-2 border rounded-lg p-4">
            <h2 className="font-medium mb-2">Результат</h2>
            {renderResult()}
          </div>
        </div>
      )}
    </main>
  );
}
