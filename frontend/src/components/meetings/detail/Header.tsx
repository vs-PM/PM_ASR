import * as React from 'react';
import { formatDate } from '@/lib/files';

type Props = {
  meetingId: number;
  filename: string;
  createdAt: string | null;
  status: string;
  progress: number | null;
};

export default function Header({ meetingId, filename, createdAt, status, progress }: Props) {
  return (
    <div className="flex items-center justify-between">
      <div className="space-y-0.5">
        <h1 className="text-xl font-semibold">Митинг #{meetingId}</h1>
        <p className="text-sm text-gray-500">
          Файл: {filename} · создано {createdAt ? formatDate(createdAt) : '—'}
        </p>
      </div>
      <div className="text-sm">
        <span className="px-2 py-1 rounded border">{status}</span>
        {typeof progress === 'number' && <span className="ml-2 text-gray-500">{progress}%</span>}
      </div>
    </div>
  );
}
