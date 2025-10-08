import * as React from 'react';

type Seg = {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  text: string | null;
};

type Props = {
  modeLabel?: string;
  segments: Seg[];
};

function fmtSec(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

export default function AudioView({ modeLabel, segments }: Props) {
  const count = segments?.length ?? 0;

  const lengths = React.useMemo(() => {
    const arr: number[] = [];
    for (const s of segments || []) {
      if (typeof s.start_ts === 'number' && typeof s.end_ts === 'number') {
        const d = s.end_ts - s.start_ts;
        if (Number.isFinite(d) && d >= 0) arr.push(d);
      }
    }
    return arr;
  }, [segments]);

  const total = lengths.reduce((a, b) => a + b, 0);
  const min = lengths.length ? Math.min(...lengths) : 0;
  const max = lengths.length ? Math.max(...lengths) : 0;
  const avg = lengths.length ? total / lengths.length : 0;

  return (
    <div className="space-y-4">
      {count === 0 ? (
        <div className="text-gray-600">
          Для режима {modeLabel ? <b>{modeLabel}</b> : '—'} пока нет нарезки.
          Запустите <b>Шаг 1: Нарезка</b>, чтобы получить сегменты.
        </div>
      ) : (
        <>
          <div className="text-gray-700">
            Нарезка выполнена для режима {modeLabel ? <b>{modeLabel}</b> : '—'}.
          </div>

          <div className="flex flex-wrap gap-2 text-sm">
            <div className="px-2 py-1 border rounded bg-gray-50">Чанков: <b>{count}</b></div>
            <div className="px-2 py-1 border rounded bg-gray-50">Суммарная длительность: <b>{fmtSec(total)}</b></div>
            <div className="px-2 py-1 border rounded bg-gray-50">Средняя длительность: <b>{fmtSec(avg)}</b></div>
            <div className="px-2 py-1 border rounded bg-gray-50">Мин: <b>{fmtSec(min)}</b></div>
            <div className="px-2 py-1 border rounded bg-gray-50">Макс: <b>{fmtSec(max)}</b></div>
          </div>

          <div className="text-xs text-gray-500">
            Подсказка: если нарезка кажется неудачной, вернитесь к шагу «Нарезка» и выберите другой режим/параметры.
          </div>
        </>
      )}
    </div>
  );
}
