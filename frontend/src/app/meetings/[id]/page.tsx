'use client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';

type MeetingDetail = {
  id: number | string;
  title?: string | null;
  status?: string | null;
  step?: string | null;
  progress?: number | null;
};

export default function MeetingCardPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const qc = useQueryClient();

    const { data, isLoading, error } = useQuery<MeetingDetail>({
    queryKey: ['meeting', id],
    queryFn: () => api<MeetingDetail>(`meetings/${id}`),
    refetchInterval: (q) =>
        q.state.data?.status === 'processing' ? 1500 : false,
    });


  const runMutation = useMutation({
    mutationFn: (payload: { seg_mode: string; diarize: boolean; do_embeddings: boolean; do_summary: boolean }) =>
      api<unknown>(`meetings/${id}/run`, { method: 'POST', body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meeting', id] }),
  });

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Митинг #{id}</h1>
      {isLoading && <p className="text-sm text-gray-600">Загрузка…</p>}
      {error && <p className="text-sm text-red-600">Ошибка загрузки</p>}
      {data && (
        <div className="space-y-6">
          <div className="border rounded-md p-4">
            <h2 className="font-medium mb-2">Быстрый запуск</h2>
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget as HTMLFormElement;
                const mode = (form.elements.namedItem('seg_mode') as HTMLSelectElement).value;
                const diarize = (form.elements.namedItem('diarize') as HTMLInputElement).checked;
                const do_embeddings = (form.elements.namedItem('do_embeddings') as HTMLInputElement).checked;
                const do_summary = (form.elements.namedItem('do_summary') as HTMLInputElement).checked;
                runMutation.mutate({ seg_mode: mode, diarize, do_embeddings, do_summary });
              }}
            >
              <label className="flex flex-col text-sm">
                Тип разделения
                <select name="seg_mode" className="border rounded-md px-2 py-1">
                  <option value="silence">По тишине</option>
                  <option value="diarization">Диаризация</option>
                  <option value="fixed">Фикс. длина</option>
                </select>
              </label>
              <label className="text-sm flex items-center gap-2">
                <input type="checkbox" name="diarize" /> Диаризация
              </label>
              <label className="text-sm flex items-center gap-2">
                <input type="checkbox" name="do_embeddings" defaultChecked /> Эмбеддинги
              </label>
              <label className="text-sm flex items-center gap-2">
                <input type="checkbox" name="do_summary" defaultChecked /> Суммаризация
              </label>
              <button className="px-3 py-2 border rounded-md">Запустить</button>
            </form>
          </div>

          <div className="border rounded-md p-4">
            <h2 className="font-medium mb-2">Статус</h2>
            <p className="text-sm">
              {data.status ?? '—'} {data.step ? `— ${data.step}` : ''}
            </p>
            {typeof data.progress === 'number' && (
              <div className="w-64 h-2 bg-gray-200 rounded mt-2">
                <div className="h-2 bg-black rounded" style={{ width: `${data.progress}%` }} />
              </div>
            )}
          </div>

          <div className="border rounded-md p-4">
            <h2 className="font-medium mb-2">Результаты (заглушка)</h2>
            <p className="text-sm text-gray-600">Табы «Транскрипт/Сегменты/Спикеры/Суммаризация/Экспорт» добавим на ANCHOR 8–9.</p>
          </div>
        </div>
      )}
    </section>
  );
}
