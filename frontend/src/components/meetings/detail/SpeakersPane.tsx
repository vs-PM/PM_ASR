import * as React from 'react';

type Sp = { id: number; speaker: string; display_name: string|null; color: string|null; is_active: boolean };

type Props = { speakers: Sp[] };

export default function SpeakersPane({ speakers }: Props) {
  if (!speakers?.length) {
    return <p className="text-sm text-gray-500">Спикеры не найдены</p>;
  }
  return (
    <div className="space-y-2">
      {speakers.map(s => (
        <div key={s.id} className="flex items-center justify-between border rounded px-3 py-2">
          <div className="flex items-center gap-3">
            <span className="inline-block w-4 h-4 rounded" style={{ background: s.color ?? '#ccc' }} />
            <div>
              <div className="font-medium">{s.display_name ?? s.speaker}</div>
              <div className="text-xs text-gray-500">{s.speaker}</div>
            </div>
          </div>
          <div className="text-xs">{s.is_active ? 'active' : 'hidden'}</div>
        </div>
      ))}
    </div>
  );
}
