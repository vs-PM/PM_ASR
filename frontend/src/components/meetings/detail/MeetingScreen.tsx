import * as React from 'react';
import { useMeetingBundle } from '@/hooks/useMeetingBundle';
import Header from './Header';
import ModesPanel from './ModesPanel';
import ResultTabs from './ResultTabs';

type Props = { meetingId: number };

export default function MeetingScreen({ meetingId }: Props) {
  const b = useMeetingBundle(meetingId);

  if (b.meeting.isLoading || b.summary.isLoading) return <p>Загрузка…</p>;
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
          status={b.globalStatus}
          progress={meta.job?.progress ?? null}
        />
        <ModesPanel
          summary={b.summary.data ?? []}
          active={b.mode}
          onSelect={b.setMode}
          onCut={b.startCut}
          onTranscribe={b.startTranscribe}
          canCut={b.canCut}
          canTranscribe={b.canTranscribe}
          cuttingNow={b.cuttingNow}
          transcribingNow={b.transcribingNow}
        />
      </div>

      <div className="lg:col-span-2 border rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-medium">Результат</h2>
          <span className="text-xs px-2 py-1 rounded border">
            Режим: <b>{b.mode}</b>
          </span>
        </div>
        <ResultTabs
          text={b.v2.data?.text ?? meta.processed_text ?? meta.raw_text ?? ''}
          segments={b.v2.data?.segments ?? []}
          speakers={b.v2.data?.speakers ?? meta.speakers ?? []}
        />
      </div>
    </div>
  );
}
