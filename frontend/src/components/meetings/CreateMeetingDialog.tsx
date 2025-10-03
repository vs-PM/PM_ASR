'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useFiles, PAGE_SIZE as FILES_PAGE_SIZE, formatBytes } from '@/lib/files';
import { useCreateMeeting } from '@/lib/meetings';


type Props = { onCreated?: (id: number) => void };


export default function CreateMeetingDialog({ onCreated }: Props) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [fileId, setFileId] = React.useState<number | null>(null);
  const [title, setTitle] = React.useState('');
  const { data: files, isLoading } = useFiles(1, FILES_PAGE_SIZE);
  const create = useCreateMeeting();

async function handleCreate() {
  if (!fileId) return;
  const res = await create.mutateAsync({
    file_id: fileId,
    meeting_id: fileId,         // ← требование бэка (временная совместимость)
    title: title || undefined,
  });
  const id = res.id;            // meeting_id из ответа
  onCreated?.(id);
  setOpen(false);
  setTitle('');
  setFileId(null);
  router.push(`/meetings/${id}`);
}

  return (
    <div>
      <button
        className="px-3 py-2 border rounded-md hover:bg-gray-50"
        onClick={() => setOpen(true)}
      >
        Создать митинг
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-4 w-[600px] max-w-[95vw]">
            <h2 className="text-lg font-semibold mb-3">Новый митинг</h2>

            <label className="block text-sm font-medium mb-1">Название (опционально)</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Например: Еженедельный синк логистики"
              className="w-full border rounded px-2 py-1 mb-3"
            />

            <label className="block text-sm font-medium mb-1">Выберите файл</label>
            <div className="border rounded max-h-[240px] overflow-auto mb-3">
              {isLoading ? (
                <div className="p-3 text-sm text-gray-500">Загрузка файлов…</div>
              ) : (files?.items ?? []).length === 0 ? (
                <div className="p-3 text-sm text-gray-500">Файлы не найдены</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white">
                    <tr>
                      <th className="text-left p-2 w-10">#</th>
                      <th className="text-left p-2">Имя</th>
                      <th className="text-right p-2">Размер</th>
                      <th className="text-center p-2 w-24">Выбор</th>
                    </tr>
                  </thead>
                  <tbody>
                    {files!.items.map((f, i) => (
                      <tr key={f.id} className="border-t">
                        <td className="p-2 text-gray-500">{i + 1}</td>
                        <td className="p-2">{f.filename}</td>
                        <td className="p-2 text-right">{formatBytes(f.size_bytes || 0)}</td>
                        <td className="p-2 text-center">
                          <input
                            type="radio"
                            name="file"
                            checked={fileId === f.id}
                            onChange={() => setFileId(f.id)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-2 rounded-md border hover:bg-gray-50"
                onClick={() => setOpen(false)}
              >
                Отмена
              </button>
              <button
                className="px-3 py-2 rounded-md border bg-black text-white hover:opacity-90 disabled:opacity-60"
                disabled={!fileId || create.isPending}
                onClick={handleCreate}
              >
                {create.isPending ? 'Создание…' : 'Создать'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
