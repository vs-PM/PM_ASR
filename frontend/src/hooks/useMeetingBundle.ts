import * as React from 'react';
import { useMeeting } from '@/lib/meetings';
import {
  SegmentMode,
  useStartSegmentationV2,
  useSegmentationState,
  useStartTranscriptionFromSegments,
  useSegments,
  useV2Result,
} from '@/lib/segmentation';

/** Единый агрегирующий хук для страницы митинга */
export function useMeetingBundle(meetingId: number) {
  // данные
  const meeting = useMeeting(meetingId);
  const segState = useSegmentationState(meetingId);
  const v2 = useV2Result(meetingId);
  const segments = useSegments(meetingId); // fallback, если v2.segments нет

  // мутации
  const doSegment = useStartSegmentationV2();
  const doTranscribe = useStartTranscriptionFromSegments();

  // локальная блокировка кнопки «Нарезать», чтобы не было двойного старта
  const [cutLocked, setCutLocked] = React.useState(false);
  const [seenProcessing, setSeenProcessing] = React.useState(false);

  const statusV2 = v2.data?.status;
  const statusMeeting = meeting.data?.status ?? meeting.data?.job?.status;
  const status: string = statusV2 ?? statusMeeting ?? '—';

  const chunks =
    typeof segState.data?.chunks === 'number'
      ? segState.data.chunks
      : (v2.data?.diarization?.length ?? 0);

  React.useEffect(() => {
    if (segState.data?.status === 'processing' || status === 'processing') {
      setSeenProcessing(true);
    }
  }, [segState.data?.status, status]);

  // один общий рефетч (стабильная ссылка, удовлетворяет eslint)
  const refetchAll = React.useCallback(() => {
    void meeting.refetch();
    void v2.refetch();
    void segState.refetch();
    void segments.refetch();
  }, [meeting.refetch, v2.refetch, segState.refetch, segments.refetch]);

  React.useEffect(() => {
    // Когда закончили processing — снимем лок, подтянем данные
    if (seenProcessing && status !== 'processing') {
      setCutLocked(false);
      refetchAll();
    }
  }, [seenProcessing, status, refetchAll]);

  const startCut = React.useCallback(
    async (mode: SegmentMode) => {
      const fileId = meeting.data?.file_id;
      if (!fileId) return;
      setCutLocked(true);
      try {
        await doSegment.mutateAsync({
          id: meetingId,
          file_id: fileId,
          meeting_id: fileId, // совместимость
          mode,
        });
        refetchAll(); // мгновенный рефетч, чтобы UI ожил быстро
      } catch {
        setCutLocked(false);
      }
    },
    [doSegment, meeting.data?.file_id, meetingId, refetchAll],
  );

  const startTranscribe = React.useCallback(async () => {
    await doTranscribe.mutateAsync({ transcript_id: meetingId });
    refetchAll();
  }, [doTranscribe, meetingId, refetchAll]);

  const cuttingNow: boolean = Boolean(
    doSegment.isPending ||
    cutLocked ||
    segState.data?.status === 'processing' ||
    status === 'processing'
  );

  const canCut: boolean = Boolean(meeting.data?.file_id) &&
    !doSegment.isPending &&
    !cutLocked &&
    status !== 'transcription_processing' &&
    segState.data?.status !== 'processing';

  const hasChunks: boolean =
    segState.data?.status === 'diarization_done' ||
    ((v2.data?.diarization?.length ?? 0) > 0);

  const canTranscribe: boolean = Boolean(
    hasChunks &&
    !doTranscribe.isPending &&
    status !== 'transcription_processing'
  );

  return {
    meeting,
    segState,
    v2,
    segments,
    status,
    chunks,
    cutLocked,
    cuttingNow,
    canCut,
    canTranscribe,
    startCut,
    startTranscribe,
    isCutPending: doSegment.isPending,
    isTranscribePending: doTranscribe.isPending,
  };
}
