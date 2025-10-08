import * as React from 'react';

type Props = {
  title?: string;
  meetingId?: number;
  filename?: string;
  createdAt?: string | null;
  status?: string;
  progress?: number | null;
};

export default function Header({ title, meetingId, filename, createdAt, status, progress }: Props) {
  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">
            {title ?? (meetingId ? `Митинг #${meetingId}` : 'Митинг')}
          </h1>
          <div className="text-xs text-gray-500">
            {filename ?? '—'}{createdAt ? ` • ${new Date(createdAt).toLocaleString()}` : ''}
          </div>
        </div>
        <div className="text-right">
          {status && <div className="text-xs px-2 py-1 border rounded inline-block">{status}</div>}
          {typeof progress === 'number' && (
            <div className="text-[10px] text-gray-500 mt-1">progress: {progress}%</div>
          )}
        </div>
      </div>
    </div>
  );
}
