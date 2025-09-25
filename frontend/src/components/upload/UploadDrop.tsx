// src/components/upload/UploadDrop.tsx
'use client';

import * as React from 'react';
import { apiUrl } from '@/lib/api';

type TaskStatus = 'queued' | 'uploading' | 'done' | 'error' | 'canceled';

type Task = {
  id: string;
  file: File;
  progress: number; // 0..100
  status: TaskStatus;
  error?: string;
  xhr?: XMLHttpRequest;
};

export type UploadDropProps = {
  onAnyFinished?: () => void;   // вызывать при успешной загрузке хотя бы одного файла
  maxParallel?: number;         // по умолчанию 2
};

export default function UploadDrop({ onAnyFinished, maxParallel = 2 }: UploadDropProps) {
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const runningRef = React.useRef(0);

  // планировщик: держим одновременно не больше maxParallel аплоадов
  React.useEffect(() => {
    const next = tasks.find(t => t.status === 'queued');
    if (!next) return;
    if (runningRef.current >= maxParallel) return;

    startUpload(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, maxParallel]);

  function pushFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    if (!arr.length) return;
    setTasks(prev => [
      ...prev,
      ...arr.map(f => ({
        id: crypto.randomUUID(),
        file: f,
        progress: 0,
        status: 'queued' as TaskStatus,
      })),
    ]);
  }

  function onSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) pushFiles(e.target.files);
    // allow re-select same file
    e.target.value = '';
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      pushFiles(e.dataTransfer.files);
    }
  }

  function prevent(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
  }

  function startUpload(t: Task) {
    const url = apiUrl('/api/v1/files/'); // важен слеш
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('f', t.file); // поле f — как в ручке бэка :contentReference[oaicite:1]{index=1}

    xhr.withCredentials = true;
    xhr.open('POST', url, true);

    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) return;
      const pct = Math.round((ev.loaded / ev.total) * 100);
      setTasks(prev => prev.map(x => x.id === t.id ? { ...x, progress: pct } : x));
    };

    xhr.onreadystatechange = () => {
      if (xhr.readyState !== 4) return;
      runningRef.current = Math.max(0, runningRef.current - 1);

      if (xhr.status >= 200 && xhr.status < 300) {
        setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: 'done', progress: 100, xhr: undefined } : x));
        onAnyFinished?.();
      } else if (xhr.status === 0) {
        // отмена
        setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: 'canceled', xhr: undefined } : x));
      } else {
        let message = `${xhr.status} ${xhr.statusText || ''}`.trim();
        try {
          if (xhr.getResponseHeader('content-type')?.includes('application/json') && xhr.responseText) {
            const j = JSON.parse(xhr.responseText) as { detail?: string; message?: string };
            message = j.detail || j.message || message;
          } else if (xhr.responseText) {
            message = xhr.responseText;
          }
        } catch {}
        setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: 'error', error: message, xhr: undefined } : x));
      }
    };

    // старт
    runningRef.current += 1;
    setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: 'uploading', xhr } : x));
    xhr.send(form);
  }

  function cancel(id: string) {
    setTasks(prev => {
      const x = prev.find(t => t.id === id);
      if (x?.xhr && x.status === 'uploading') x.xhr.abort();
      return prev.map(t => t.id === id ? { ...t, status: 'canceled', xhr: undefined } : t);
    });
  }

  function clearFinished() {
    setTasks(prev => prev.filter(t => t.status === 'uploading' || t.status === 'queued'));
  }

  // UI
  return (
    <div className="space-y-4">
      <div
        onDragEnter={prevent}
        onDragOver={prevent}
        onDragLeave={prevent}
        onDrop={onDrop}
        className="rounded-2xl border-2 border-dashed p-8 text-center cursor-pointer hover:bg-gray-50"
        onClick={() => inputRef.current?.click()}
        role="button"
        aria-label="Выберите файл или перетащите сюда"
      >
        <p className="text-lg font-medium">Перетащите аудио сюда или кликните, чтобы выбрать</p>
        <p className="text-sm text-gray-500 mt-1">Поддерживаются любые форматы — дальше обработаем через FFmpeg</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          // принимаем всё
          onChange={onSelect}
        />
      </div>

      {tasks.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">Загрузки</h3>
            <button onClick={clearFinished} className="text-sm px-2 py-1 border rounded-md hover:bg-gray-50">
              Очистить завершённые
            </button>
          </div>
          <ul className="space-y-2">
            {tasks.map(t => (
              <li key={t.id} className="border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{t.file.name}</p>
                    <p className="text-xs text-gray-500">{(t.file.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {t.status === 'uploading' && (
                      <button onClick={() => cancel(t.id)} className="text-xs px-2 py-1 border rounded-md hover:bg-gray-50">
                        Отменить
                      </button>
                    )}
                    {t.status === 'error' && (
                      <span className="text-xs text-red-600" title={t.error}>
                        Ошибка
                      </span>
                    )}
                    {t.status === 'done' && <span className="text-xs text-green-600">Готово</span>}
                    {t.status === 'canceled' && <span className="text-xs text-gray-500">Отменено</span>}
                  </div>
                </div>

                {/* прогресс */}
                <div className="mt-2 h-2 w-full bg-gray-200 rounded">
                  <div
                    className="h-2 rounded bg-black transition-all"
                    style={{ width: `${t.progress}%` }}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={t.progress}
                  />
                </div>

                {t.status === 'error' && t.error && (
                  <p className="mt-1 text-xs text-red-600">{t.error}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
