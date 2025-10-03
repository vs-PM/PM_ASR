import * as React from 'react';
import type { SegmentMode } from '@/lib/segmentation';

type Props = {
  segStatus: string;
  chunks: number;
  canCut: boolean;
  cuttingNow: boolean;
  onCut: (mode: SegmentMode) => Promise<void> | void;
  canTranscribe: boolean;
  transcribingNow: boolean;
  onTranscribe: () => Promise<void> | void;
};

export default function SegmentationPanel(props: Props) {
  const {
    segStatus, chunks, canCut, cuttingNow, onCut,
    canTranscribe, transcribingNow, onTranscribe,
  } = props;

  const [mode, setMode] = React.useState<SegmentMode>('diarize');

  const disableRadios = cuttingNow;

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <h2 className="font-medium">Шаг 1: Нарезка</h2>

      <div className="space-y-1 text-sm">
        {(['full','vad','fixed','diarize'] as SegmentMode[]).map(m => (
          <label key={m} className="flex items-center gap-2">
            <input
              type="radio"
              name="mode"
              value={m}
              checked={mode === m}
              onChange={() => setMode(m)}
              disabled={disableRadios}
            />
            {labelFor(m)}
          </label>
        ))}
      </div>

      <button
        className="w-full px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
        disabled={!canCut}
        onClick={() => onCut(mode)}
      >
        {cuttingNow ? 'Нарезаю…' : 'Нарезать'}
      </button>

      <div className="text-xs text-gray-600">
        Статус нарезки: <span className="font-medium">{segStatus}</span>
        <span className="ml-2">Чанки: <span className="font-medium">{chunks}</span></span>
      </div>

      <h2 className="font-medium mt-4">Шаг 2: Транскрипция</h2>
      <button
        className="w-full px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
        disabled={!canTranscribe}
        onClick={onTranscribe}
      >
        {transcribingNow ? 'Запускаю…' : 'Запустить транскрипцию'}
      </button>
    </div>
  );
}

function labelFor(m: SegmentMode): string {
  switch (m) {
    case 'full': return 'Файл целиком';
    case 'vad': return 'По тишине (VAD)';
    case 'fixed': return 'Фикс. окна по 30с';
    case 'diarize': return 'Диаризация (спикеры)';
  }
}
