import * as React from 'react';
import { fmtTime } from '@/lib/meetings';

type Seg = { id: number; start_ts: number|null; end_ts: number|null; text: string; speaker: string|null; lang: string|null };

type Props = { segments: Seg[] };

export default function SegmentsPane({ segments }: Props) {
  const [q, setQ] = React.useState('');
  const rx = React.useMemo(() => {
    try { return q ? new RegExp(q, 'i') : null; } catch { return null; }
  }, [q]);

  const rows = React.useMemo(() => {
    if (!rx) return segments;
    return segments.filter(r =>
      (r.text && rx.test(r.text)) ||
      (r.speaker && rx.test(r.speaker)) ||
      (r.lang && rx.test(r.lang))
    );
  }, [segments, rx]);

  return (
    <div>
      <div className="mb-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Фильтр по сегментам…"
          className="border rounded px-2 py-1 w-full"
        />
      </div>

      <div className="overflow-auto">
        <table className="w-full text-sm">
          <thead className="text-left sticky top-0 bg-white">
            <tr>
              <th className="py-2 pr-2">#</th>
              <th className="py-2 pr-2">Начало</th>
              <th className="py-2 pr-2">Конец</th>
              <th className="py-2 pr-2">Спикер</th>
              <th className="py-2 pr-2">Язык</th>
              <th className="py-2">Текст</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id} className="border-t align-top">
                <td className="py-2 pr-2 text-gray-500">{i + 1}</td>
                <td className="py-2 pr-2 tabular-nums">{fmtTime(r.start_ts ?? 0)}</td>
                <td className="py-2 pr-2 tabular-nums">{fmtTime(r.end_ts ?? 0)}</td>
                <td className="py-2 pr-2">{r.speaker ?? '—'}</td>
                <td className="py-2 pr-2">{r.lang ?? '—'}</td>
                <td className="py-2 whitespace-pre-wrap">{r.text}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="py-6 text-center text-gray-500">
                  Сегментов пока нет.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
