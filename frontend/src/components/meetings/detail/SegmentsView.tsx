import * as React from 'react';

type Seg = {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  text: string | null;
  speaker?: string | null;
  lang?: string | null;
};

type Props = {
  status: string;       // queued | diarize_done | transcription_done | summary_processing | summary_done
  modeLabel?: string;   // подпись режима
  segments: Seg[];
};

function formatTs(v: number | null) {
  if (v == null) return '—';
  const s = Math.max(0, Math.floor(v));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

export default function SegmentsView({ status, modeLabel, segments }: Props) {
  const hasAnySegments = segments && segments.length > 0;

  return (
    <div className="space-y-4">
      {/* Подсказка по состоянию */}
      <div className="text-sm">
        {status === 'queued' && (
          <div className="text-gray-600">
            Для режима {modeLabel ? <b>{modeLabel}</b> : '—'} пока нет сегментов.
            Сначала выполните <b>Нарезку</b>.
          </div>
        )}
        {status === 'diarize_done' && (
          <div className="text-gray-600">
            Сегменты готовы. Запустите <b>Транскрипцию</b> для получения текста.
          </div>
        )}
        {status === 'transcription_done' && (
          <div className="text-gray-600">Транскрипция выполнена. Ниже — разбивка по сегментам.</div>
        )}
        {status === 'summary_processing' && (
          <div className="text-gray-600">
            Идёт создание протокола. Вкладка «Протокол» покажет результат по завершении.
          </div>
        )}
        {status === 'summary_done' && (
          <div className="text-gray-600">
            Протокол готов. Переключитесь на вкладку «Протокол», чтобы посмотреть результат.
          </div>
        )}
      </div>

      {/* Таблица сегментов */}
      {hasAnySegments ? (
        <div className="overflow-auto border rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 w-16">#</th>
                <th className="text-left px-3 py-2 w-20">Начало</th>
                <th className="text-left px-3 py-2 w-20">Конец</th>
                <th className="text-left px-3 py-2 w-28">Спикер</th>
                <th className="text-left px-3 py-2">Текст</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((s, i) => (
                <tr key={s.id} className="border-t align-top">
                  <td className="px-3 py-2">{i + 1}</td>
                  <td className="px-3 py-2">{formatTs(s.start_ts)}</td>
                  <td className="px-3 py-2">{formatTs(s.end_ts)}</td>
                  <td className="px-3 py-2">
                    {(s.speaker || '').trim() || <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    {(s.text || '').trim() || <span className="text-gray-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-gray-500">Сегментов пока нет.</div>
      )}
    </div>
  );
}
