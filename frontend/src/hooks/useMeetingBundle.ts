import * as React from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useMeeting } from '@/lib/meetings';
import {
  SegmentMode,
  ALL_MODES,
  useAllModesState,
  useStartSegmentationV2,
  useStartTranscriptionFromSegments,
  useV2Result,
} from '@/lib/segmentation';

export function useMeetingBundle(meetingId: number) {
  const qc = useQueryClient();

  // активный режим
  const [mode, setMode] = React.useState<SegmentMode>('diarize');

  // Деталь митинга (старый источник)
  const meeting = useMeeting(meetingId);
  const transcriptId = meeting.data?.id ?? meetingId;

  // Состояние ВСЕХ режимов (разом; без поллинга/мигания)
  const modesState = useAllModesState(transcriptId);

  // Результат по выбранному режиму
  const v2 = useV2Result(transcriptId, mode);

  // Найти данные по текущему режиму
  const current = React.useMemo(() => {
    const arr = modesState.data ?? [];
    return arr.find((x) => x.mode === mode) ?? { mode, status: 'queued', chunks: 0 };
  }, [modesState.data, mode]);

  const chunks = current.chunks;
  const segStatus = current.status;
  const cutting = segStatus === 'processing';

  // локальный флаг «только что транскрибировали» — чтобы выключить кнопку до ручного refresh
  const [justTranscribedByMode, setJustTranscribedByMode] = React.useState<Record<SegmentMode, boolean>>({
    diarize: false, vad: false, fixed: false, full: false,
  });

  const hasResult =
    (v2.data?.segments && v2.data.segments.length > 0) ||
    Boolean((v2.data?.text ?? '').trim());

  const startSeg = useStartSegmentationV2();
  const startAsr = useStartTranscriptionFromSegments();

  const canCut = !cutting && chunks === 0;
  const canTranscribe =
    chunks > 0 &&
    !cutting &&
    !hasResult &&
    !startAsr.isPending &&
    !justTranscribedByMode[mode];

  async function startCut() {
    const fileId = meeting.data?.file_id;
    if (!fileId || !transcriptId) return;
    await startSeg.mutateAsync({ id: transcriptId, file_id: fileId, mode });
  }

  async function startTranscribe() {
    if (!transcriptId) return;
    await startAsr.mutateAsync({ transcript_id: transcriptId, mode });
    setJustTranscribedByMode((m) => ({ ...m, [mode]: true }));
  }

  // Ручное обновление по кнопке (ws позже)
  async function refresh() {
    if (!transcriptId) return;
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['segmentation-summary', transcriptId] }),
      qc.invalidateQueries({ queryKey: ['v2-result', transcriptId, mode] }),
      qc.invalidateQueries({ queryKey: ['meeting'] }),
    ]);
    setJustTranscribedByMode({ diarize: false, vad: false, fixed: false, full: false });
  }

  // Summary — для панели статусов (все режимы сразу)
  const summary = React.useMemo(() => {
    const arr = modesState.data ?? ALL_MODES.map((m) => ({ mode: m, status: 'queued', chunks: 0 }));
    return {
      data: arr,
      isLoading: modesState.isLoading,
      isError: modesState.isError,
    };
  }, [modesState.data, modesState.isLoading, modesState.isError]);

  const globalStatus = meeting.data?.status ?? 'queued';

  return {
    // UI
    mode, setMode,

    // данные
    meeting,
    v2,
    summary,

    // производные
    chunks,
    segStatus,
    cuttingNow: cutting || startSeg.isPending,
    transcribingNow: startAsr.isPending,
    canCut,
    canTranscribe,
    globalStatus,

    // действия
    startCut,
    startTranscribe,
    refresh,
  };
}
