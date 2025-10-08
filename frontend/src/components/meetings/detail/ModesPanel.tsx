import * as React from 'react';
import type { SegmentMode } from '@/lib/segmentation';

type ModeState = { mode: SegmentMode; status: string; chunks: number };

type Props = {
  summary: ModeState[];
  active: SegmentMode;
  onSelect: (m: SegmentMode) => void;
  onCut: () => void;
  onTranscribe: () => void;
  canCut: boolean;
  canTranscribe: boolean;
  cuttingNow: boolean;
  transcribingNow: boolean;
  onCreateProtocol: () => void;
  creatingNow: boolean;
};

const TITLES: Record<SegmentMode, string> = {
  full: 'Файл целиком',
  vad: 'По тишине (VAD)',
  fixed: 'Фикс. окна по 30с',
  diarize: 'Диаризация (спикеры)',
};

export default function ModesPanel({
  summary,
  active,
  onSelect,
  onCut,
  onTranscribe,
  canCut,
  canTranscribe,
  cuttingNow,
  transcribingNow,
  creatingNow,
  onCreateProtocol
}: Props) {
  const modes: SegmentMode[] = ['full', 'vad', 'fixed', 'diarize'];

  return (
    <div className="border rounded-lg p-4 space-y-4">
      <h2 className="font-medium"> (выбери режим)</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {modes.map(m => {
          const s = summary.find(x => x.mode === m) ?? { mode: m, status: 'queued', chunks: 0 };
          const isActive = active === m;
          return (
            <button
              key={m}
              onClick={() => onSelect(m)}
              className={`text-left border rounded-lg p-3 hover:bg-gray-50 ${isActive ? 'ring-2 ring-black' : ''}`}
            >
              <div className="font-medium">{TITLES[m]}</div>
              <div className="text-xs text-gray-600 mt-1">
                Статус: <span className="font-medium">{s.status}</span>
                <span className="ml-2">Чанки: <span className="font-medium">{s.chunks}</span></span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex gap-3">
        <button
          className="flex-1 px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
          disabled={!canCut}
          onClick={onCut}
        >
          {cuttingNow ? 'Нарезаю…' : 'Нарезать выбранный режим'}
        </button>
        <button
          className="flex-1 px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
          disabled={!canTranscribe}
          onClick={onTranscribe}
        >
          {transcribingNow ? 'Запускаю…' : 'Транскрибировать по выбранному режиму'}
        </button>
        <button
          className="flex-1 px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
          onClick={onCreateProtocol}
          disabled={!onCreateProtocol || !!creatingNow}
        >
          {creatingNow ? 'Создаю протокол…' : 'Создать протокол'}
        </button>
      </div>

      <p className="text-xs text-gray-500">
        Нарезка доступна отдельно для каждого режима. Если для режима уже есть чанки, повторная нарезка не запускается.
      </p>
    </div>
  );
}
