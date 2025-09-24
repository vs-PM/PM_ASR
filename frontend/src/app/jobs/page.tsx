'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

type RunRow = {
  id: number | string;
  meeting_id?: number | string | null;
  step?: string | null;
  status?: string | null;
  progress?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
};
type RunsList = { items: RunRow[] };

export default function JobsPage() {
  const { data, isLoading, error, refetch } = useQuery<RunsList>({
    queryKey: ['runs'],
    queryFn: () => api<RunsList>('runs?limit=50'),
    refetchInterval: 5000,
  });

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Задачи</h1>
        <button className="px-3 py-2 border rounded-md" onClick={() => refetch()}>
          Обновить
        </button>
      </div>
      {isLoading && <p className="text-sm text-gray-600">Загрузка…</p>}
      {error && <p className="text-sm text-red-600">Ошибка загрузки</p>}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-2">ID</th>
            <th>Митинг</th>
            <th>Шаг</th>
            <th>Статус</th>
            <th>Прогресс</th>
            <th>Начало</th>
            <th>Конец</th>
          </tr>
        </thead>
        <tbody>
          {data?.items?.length ? (
            data.items.map((r) => (
              <tr key={r.id} className="border-b">
                <td className="py-2">{r.id}</td>
                <td>{r.meeting_id}</td>
                <td>{r.step}</td>
                <td>{r.status}</td>
                <td>{typeof r.progress === 'number' ? `${r.progress}%` : '—'}</td>
                <td>{r.started_at ?? '—'}</td>
                <td>{r.finished_at ?? '—'}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="py-4 text-gray-600" colSpan={7}>
                Нет задач
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
