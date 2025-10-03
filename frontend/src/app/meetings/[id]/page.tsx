'use client';

import * as React from 'react';
import { useParams } from 'next/navigation';
import MeetingScreen from '@/components/meetings/detail/MeetingScreen';

export default function MeetingDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  if (!Number.isFinite(id) || id <= 0) {
    return <main className="p-6">Некорректный id</main>;
  }

  return (
    <main className="p-6">
      <MeetingScreen meetingId={id} />
    </main>
  );
}
