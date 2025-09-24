'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

type FileRow = {
  id: number | string;
  name?: string;
  filename?: string;
  duration?: number | string | null;
  size?: number | null;
  uploaded_at?: string | null;
  status?: string | null;
};

type FilesList = { items: FileRow[] };

export default function AudioPage() {
  const { data, isLoading, error, refetch } = useQuery<FilesList>({
    queryKey: ['files'],
    queryFn: () => api<FilesList>('files'),
  });

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Аудиофайлы</h1>
        <button className="px-3 py-2 border rounded-md" onClick={() => refetch()}>
          Обновить
        </button>
      </div>

      <div className="border rounded-md p-6 text-center text-sm text-gray-600">
        <p>Drag & Drop загрузку добавим на ANCHOR 4. Сейчас отображается список.</p>
      </div>

      {isLoading && <p className="text-sm text-gray-600">Загрузка…</p>}
      {error && <p className="text-sm text-red-600">Ошибка загрузки</p>}

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-2">Имя</th>
            <th>Длительность</th>
            <th>Размер</th>
            <th>Загружен</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {data?.items?.length ? (
            data.items.map((f) => (
              <tr key={f.id} className="border-b">
                <td className="py-2">{f.name || f.filename}</td>
                <td>{f.duration ?? '—'}</td>
                <td>{typeof f.size === 'number' ? `${Math.round(f.size / 1024)} KB` : '—'}</td>
                <td>{f.uploaded_at ?? '—'}</td>
                <td>{f.status ?? 'ready'}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="py-4 text-gray-600" colSpan={5}>
                Нет файлов
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
