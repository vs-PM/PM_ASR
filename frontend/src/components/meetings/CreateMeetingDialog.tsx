// src/components/meetings/CreateMeetingDialog.tsx
'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useFiles, PAGE_SIZE as FILES_PAGE_SIZE, formatBytes } from '@/lib/files';
import { useCreateMeeting } from '@/lib/meetings';

type Props = { onCreated?: (id: number) => void };

export default function CreateMeetingDialog({ onCreated }: Props) {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [page, setPage] = React.useState(1);
  const [fileId, setFileId] = React.useState<number | null>(null);
  const [title, setTitle] = React.useState('');
  const files = useFiles(page, FILES_PAGE_SIZE);
  const create = useCreateMeeting();

  function reset() {
    setFileId(null);
    setTitle('');
  }

  async function submit() {
    if (fileId == null) return;
    const res = await create.mutateAsync({ file_id: fileId, title: title || undefined });
    const id = res.id;
    onCreated?.(id);
    setOpen(false);
    reset();
    router.push(`/meetings/${id}`);
  }

  return (
    <div>
      <button className="px-3 py-2 border rounded-md text-sm hover:bg-gray-50" onClick={() => setOpen(true)}>
        Создать митинг
      </button>

      {open && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4" onClick={() => setOpen(false)}>
          <div className="w-full max-w-3xl rounded-2xl bg-white p-4 shadow-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-medium">Новый митинг</h3>
              <button className="text-sm px-2 py-1 border rounded-md" onClick={() => setOpen(false)}>
                Закрыть
              </button>
            </div>

            <div className="grid md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <div className="mb-2 font-medium">Выберите файл из загруженных</div>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-3 py-2">Файл</th>
                        <th className="text-left px-3 py-2">Размер</th>
                        <th className="text-left px-3 py-2">Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      {files.isLoading ? (
                        <tr>
                          <td className="px-3 py-3" colSpan={3}>
                            Загружаем…
                          </td>
                        </tr>
                      ) : files.isError ? (
                        <tr>
                          <td className="px-3 py-3 text-red-600" colSpan={3}>
                            {(files.error as Error).message}
                          </td>
                        </tr>
                      ) : (files.data?.items ?? []).length === 0 ? (
                        <tr>
                          <td className="px-3 py-3 text-gray-500" colSpan={3}>
                            Нет загруженных файлов
                          </td>
                        </tr>
                      ) : (
                        files.data!.items.map((f) => (
                          <tr key={f.id} className={fileId === f.id ? 'bg-gray-50' : ''}>
                            <td className="px-3 py-2">{f.filename}</td>
                            <td className="px-3 py-2 whitespace-nowrap">{formatBytes(f.size_bytes)}</td>
                            <td className="px-3 py-2">
                              <button
                                className="text-xs px-2 py-1 border rounded-md hover:bg-gray-100"
                                onClick={() => setFileId(f.id)}
                                aria-pressed={fileId === f.id}
                              >
                                {fileId === f.id ? 'Выбрано' : 'Выбрать'}
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="mt-2 flex items-center justify-end gap-2">
                  <button
                    className="px-2 py-1 border rounded-md text-xs"
                    disabled={(files.data?.items?.length ?? 0) === 0 || page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    ← Назад
                  </button>
                  <span className="text-xs">Стр. {page}</span>
                  <button
                    className="px-2 py-1 border rounded-md text-xs"
                    disabled={(files.data?.items?.length ?? 0) < FILES_PAGE_SIZE}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Вперёд →
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-sm font-medium">Название (опционально)</label>
                  <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="mt-1 w-full border rounded px-2 py-1"
                    placeholder="Напр. «Встреча с клиентом»"
                  />
                </div>

                <button
                  disabled={fileId == null || create.isPending}
                  onClick={submit}
                  className="w-full px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
                >
                  {create.isPending ? 'Создаём…' : 'Создать митинг'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
