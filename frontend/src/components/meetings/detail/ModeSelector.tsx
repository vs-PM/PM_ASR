import * as React from 'react';
import type { SegmentMode } from '@/lib/segmentation';

type Props = {
  mode: SegmentMode;
  onChange: (m: SegmentMode) => void;
};

const MODES: Array<{ value: SegmentMode; label: string; sub?: string }> = [
  { value: 'full',    label: 'Файл целиком' },
  { value: 'vad',     label: 'По тишине (VAD)' },
  { value: 'fixed',   label: 'Фикс. окна по 30с' },
  { value: 'diarize', label: 'Диаризация (спикеры)' },
];

export default function ModeSelector({ mode, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {MODES.map(m => {
        const active = m.value === mode;
        return (
          <button
            key={m.value}
            onClick={() => onChange(m.value)}
            className={[
              'px-3 py-2 rounded-md border text-sm',
              active
                ? 'border-black bg-black text-white'
                : 'border-gray-300 hover:bg-gray-50'
            ].join(' ')}
            aria-pressed={active}
          >
            <div className="leading-none">{m.label}</div>
            {m.sub && <div className="text-[11px] opacity-70 mt-0.5">{m.sub}</div>}
          </button>
        );
      })}
    </div>
  );
}
