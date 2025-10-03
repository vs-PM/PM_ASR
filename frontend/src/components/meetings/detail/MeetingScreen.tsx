import * as React from 'react';
import { useMeetingBundle } from '@/hooks/useMeetingBundle';
import Header from './Header';
import SegmentationPanel from './SegmentationPanel';
import ResultTabs from './ResultTabs';

type Props = { meetingId: number };

export default function MeetingScreen({ meetingId }: Props) {
  const b = useMeetingBundle(meetingId);

  if (b.meeting.isLoading) return <p>Загрузка…</p>;
  if (b.meeting.isError) return <div className="text-red-600">Ошибка: {b.meeting.error?.message}</div>;
  if (!b.meeting.data) return <p>Не найдено</p>;

  const meta = b.meeting.data;

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-1 space-y-4">
        <Header
          meetingId={meta.meeting_id}
          filename={meta.filename ?? '—'}
          createdAt={meta.created_at ?? null}
          status={b.status}
          progress={meta.job?.progress ?? null}
        />
        <SegmentationPanel
          segStatus={b.segState.data?.status ?? '—'}
          chunks={b.chunks}
          canCut={b.canCut}
          cuttingNow={b.cuttingNow}
          onCut={b.startCut}
          canTranscribe={Boolean(b.canTranscribe)}
          transcribingNow={b.isTranscribePending}
          onTranscribe={b.startTranscribe}
        />
      </div>

      <div className="lg:col-span-2 border rounded-lg p-4">
        <h2 className="font-medium mb-2">Результат</h2>
        <ResultTabs
          text={b.v2.data?.text ?? meta.processed_text ?? meta.raw_text ?? ''}
          segments={b.v2.data?.segments ?? b.segments.data?.items ?? []}
          speakers={b.v2.data?.speakers ?? meta.speakers ?? []}
        />
      </div>
    </div>
  );
}
