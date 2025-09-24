'use client';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { api } from '@/lib/api';

type MeetingRow = {
  id: number | string;
  title?: string | null;
  audio_file_name?: string | null;
  audio_file_id?: number | string | null;
  status?: string | null;
  progress?: number | null;
  updated_at?: string | null;
};

type MeetingsList = { items: MeetingRow[] };

export default function MeetingsPage() {
  const { data, isLoading, error, refetch } = useQuery<MeetingsList>({
  queryKey: ['meetings'],
  queryFn: () => api<MeetingsList>('meetings'),
  refetchInterval: (q) =>
    q.state.data?.items?.some((m) => m.status === 'processing') ? 1500 : false,
  });


  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Митинги</h1>
        <div className="flex items-center gap-2">
          <Link href="/meetings/new" className="px-3 py-2 border rounded-md">
            Создать
          </Link>
          <button className="px-3 py-2 border rounded-md" onClick={() => refetch()}>
            Обновить
          </button>
        </div>
      </div>

      {isLoading && <p className="text-sm text-gray-600">Загрузка…</p>}
      {error && <p className="text-sm text-red-600">Ошибка загрузки</p>}

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-2">Название</th>
            <th>Файл</th>
            <th>Статус</th>
            <th>Прогресс</th>
            <th>Обновлён</th>
          </tr>
        </thead>
        <tbody>
          {data?.items?.length ? (
            data.items.map((m) => (
              <tr key={m.id} className="border-b">
                <td className="py-2">
                  <Link href={`/meetings/${m.id}`} className="underline">
                    {m.title || `Митинг #${m.id}`}
                  </Link>
                </td>
                <td>{m.audio_file_name ?? m.audio_file_id ?? '—'}</td>
                <td>{m.status ?? '—'}</td>
                <td>
                  {typeof m.progress === 'number' ? (
                    <div className="w-32 h-2 bg-gray-200 rounded">
                      <div className="h-2 bg-black rounded" style={{ width: `${m.progress}%` }} />
                    </div>
                  ) : (
                    '—'
                  )}
                </td>
                <td>{m.updated_at ?? '—'}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="py-4 text-gray-600" colSpan={5}>
                Нет митингов
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
