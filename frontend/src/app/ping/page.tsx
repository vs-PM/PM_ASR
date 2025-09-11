'use client';

import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/health/StatusBadge';
import { CheckCard } from '@/components/health/CheckCard';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Activity, Database, Cpu, HardDrive, Network, TimerReset } from 'lucide-react';
import { useMemo, useState } from 'react';

type HealthResp = {
  status: 'ok' | 'degraded' | string;
  time: { started_at: string; uptime_sec: number };
  system: { python: string; platform: string; device?: string };
  checks: {
    db?: { ok: boolean; msg?: string };
    ollama?: { ok: boolean; msg?: string; url?: string };
    ffmpeg?: { ok: boolean; msg?: string };
    cuda?: { available?: boolean; cuda?: string | null; cudnn?: number | null; error?: string };
  };
};

function fmtUptime(sec?: number) {
  if (!sec && sec !== 0) return '-';
  const s = Math.floor(sec);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return [
    d ? `${d}д` : null,
    h ? `${h}ч` : null,
    m ? `${m}м` : null,
    `${ss}с`,
  ].filter(Boolean).join(' ');
}

export default function PingPage() {
  const [auto, setAuto] = useState(true);

  const q = useQuery({
    queryKey: ['healthz'],
    queryFn: () => api<HealthResp>('/api/v1/healthz'),
    refetchInterval: auto ? 5000 : false, // автообновление раз в 5с
  });

  const startedAt = useMemo(() => {
    try {
      return new Intl.DateTimeFormat('ru-RU', {
        dateStyle: 'medium', timeStyle: 'medium'
      }).format(new Date(q.data?.time.started_at ?? ''));
    } catch { return q.data?.time.started_at || '-'; }
  }, [q.data?.time.started_at]);

  const lastUpdated = useMemo(() => {
    if (!q.dataUpdatedAt) return '-';
    return new Intl.DateTimeFormat('ru-RU', {
      timeStyle: 'medium'
    }).format(new Date(q.dataUpdatedAt));
  }, [q.dataUpdatedAt]);

  const cudaLine = useMemo(() => {
    const c = q.data?.checks.cuda;
    if (!c) return '-';
    if (c.error) return `error: ${c.error}`;
    const parts = [];
    parts.push(c.available ? 'GPU: да' : 'GPU: нет');
    if (c.cuda)  parts.push(`CUDA ${c.cuda}`);
    if (c.cudnn) parts.push(`cuDNN ${c.cudnn}`);
    return parts.join(' · ');
  }, [q.data?.checks.cuda]);

  return (
    <div className="px-6 py-6 space-y-6">
      {/* Заголовок */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Activity className="w-6 h-6 text-yellow-500" />
          Состояние сервиса
        </h1>
        <StatusBadge status={q.data?.status} />
        <div className="ml-auto flex items-center gap-2">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              className="accent-yellow-500"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />
            Автообновление (5с)
          </label>
          <Button size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>
            <TimerReset className="w-4 h-4 mr-2" />
            Обновить
          </Button>
        </div>
      </div>

      {/* Верхняя сводка */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Система</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div><span className="text-gray-500">Python:</span> {q.data?.system.python || '-'}</div>
            <div><span className="text-gray-500">Платформа:</span> {q.data?.system.platform || '-'}</div>
            <div><span className="text-gray-500">Устройство:</span> {q.data?.system.device || '-'}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Время</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div><span className="text-gray-500">Старт:</span> {startedAt}</div>
            <div><span className="text-gray-500">Аптайм:</span> {fmtUptime(q.data?.time.uptime_sec)}</div>
            <div className="text-xs text-gray-500">Последнее обновление UI: {lastUpdated}</div>
          </CardContent>
        </Card>
      </div>

      {/* Проверки */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <CheckCard
          title="База данных"
          ok={q.data?.checks.db?.ok}
          message={q.data?.checks.db?.msg}
          icon={<Database className="w-4 h-4 text-yellow-500" />}
        />

        <CheckCard
          title="Ollama"
          ok={q.data?.checks.ollama?.ok}
          message={q.data?.checks.ollama?.msg}
          icon={<Network className="w-4 h-4 text-yellow-500" />}
        >
          <div className="text-xs text-gray-500 break-all">
            {q.data?.checks.ollama?.url}
          </div>
        </CheckCard>

        <CheckCard
          title="FFmpeg"
          ok={q.data?.checks.ffmpeg?.ok}
          message={q.data?.checks.ffmpeg?.msg}
          icon={<HardDrive className="w-4 h-4 text-yellow-500" />}
        />

        <CheckCard
          title="CUDA"
          ok={q.data?.checks.cuda?.available}
          message={cudaLine}
          icon={<Cpu className="w-4 h-4 text-yellow-500" />}
        />
      </div>

      {/* Сырой JSON (по желанию) */}
      <details className="mt-2">
        <summary className="cursor-pointer select-none text-sm text-gray-600">
          Показать сырой JSON
        </summary>
        <pre className="mt-2 p-3 bg-gray-100 rounded text-xs overflow-auto">
          {q.isLoading ? 'Загрузка…' : JSON.stringify(q.data, null, 2)}
        </pre>
      </details>

      {/* Ошибки запроса */}
      {q.isError && (
        <div className="text-sm text-red-600">
          Не удалось получить статус: {(q.error as Error)?.message}
        </div>
      )}
    </div>
  );
}
