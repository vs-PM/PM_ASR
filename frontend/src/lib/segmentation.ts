// src/lib/segmentation.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';

export type SegmentMode = 'full' | 'vad' | 'fixed' | 'diarize';

export type SegmentStartIn = {
  id: number;            // PK транскрипта = id митинга
  file_id: number;       // привязанный файл
  mode: SegmentMode;     // режим нарезки
  meeting_id?: number;   // совместимость: можно прислать = file_id, бэк игнорирует для поиска
};

export type SegmentStartOut = {
  transcript_id: number;
  status: string;        // "processing"
  mode: SegmentMode;
  chunks?: number | null;
};

export type SegmentStateOut = {
  transcript_id: number;
  status: string;        // "processing" | "diarization_done" | "error" | ...
  chunks: number;        // количество интервалов (MfgDiarization)
};

export type TranscriptionStartOut = {
  transcript_id: number;
  status: string;        // "transcription_processing"
};

export type SegmentListItem = {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  text: string;
  speaker: string | null;
  lang: string | null;
};

export type SegmentList = {
  items: SegmentListItem[];
  total: number;
};

export type V2Result = {
  transcript_id: number;
  status: string;
  filename?: string | null;
  file_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  text?: string | null;
  diarization: { id: number; start_ts: number | null; end_ts: number | null; speaker: string | null }[];
  speakers: { id: number; speaker: string; display_name: string | null; color: string | null; is_active: boolean }[];
  segments: { id: number; start_ts: number | null; end_ts: number | null; text: string; speaker: string | null; lang: string | null }[];
};

/* ---------- v2: сегментация ---------- */

export async function startSegmentationV2(body: SegmentStartIn): Promise<SegmentStartOut> {
  // путь БЕЗ завершающего слэша
  return api<SegmentStartOut>('/api/v2/segment', { method: 'POST', body });
}

export function useStartSegmentationV2() {
  const qc = useQueryClient();
  return useMutation<SegmentStartOut, Error, SegmentStartIn>({
    mutationFn: (payload) => startSegmentationV2(payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['meeting', res.transcript_id] });
      qc.invalidateQueries({ queryKey: ['segmentation', res.transcript_id] });
      qc.invalidateQueries({ queryKey: ['meetings'] });
    },
  });
}

export async function fetchSegmentationState(transcriptId: number): Promise<SegmentStateOut> {
  return api<SegmentStateOut>(`/api/v2/segment/${transcriptId}`);
}

export function useSegmentationState(transcriptId: number | null | undefined) {
  return useQuery<SegmentStateOut, Error>({
    queryKey: ['segmentation', transcriptId],
    queryFn: () => fetchSegmentationState(transcriptId as number),
    enabled: typeof transcriptId === 'number' && transcriptId > 0,
    refetchInterval: (q) => {
      const d = q.state.data as SegmentStateOut | undefined;
      return d && d.status === 'processing' ? 1500 : false;
    },
    staleTime: 1000,
  });
}

export async function startTranscriptionFromSegments(transcriptId: number): Promise<TranscriptionStartOut> {
  return api<TranscriptionStartOut>(`/api/v2/segment/transcription/${transcriptId}`, { method: 'POST' });
}

export function useStartTranscriptionFromSegments() {
  const qc = useQueryClient();
  return useMutation<TranscriptionStartOut, Error, { transcript_id: number }>({
    mutationFn: ({ transcript_id }) => startTranscriptionFromSegments(transcript_id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['meeting', res.transcript_id] });
      qc.invalidateQueries({ queryKey: ['segmentation', res.transcript_id] });
      qc.invalidateQueries({ queryKey: ['segments', res.transcript_id] });
      qc.invalidateQueries({ queryKey: ['meetings'] });
    },
  });
}

/* ---------- (опционально) текстовые сегменты после ASR ---------- */

export async function fetchSegmentsList(transcriptId: number): Promise<SegmentList> {
  try {
    return await api<SegmentList>(`/api/v1/transcripts/${transcriptId}/segments`);
  } catch (e: unknown) {
    const msg = (e as { message?: string })?.message ?? '';
    if (/404|not found/i.test(msg)) return { items: [], total: 0 };
    throw e;
  }
}

export function useSegments(transcriptId: number | null | undefined) {
  return useQuery<SegmentList, Error>({
    queryKey: ['segments', transcriptId],
    queryFn: () => fetchSegmentsList(transcriptId as number),
    enabled: typeof transcriptId === 'number' && transcriptId > 0,
    staleTime: 2000,
  });
}

export async function fetchV2Result(transcriptId: number): Promise<V2Result> {
  return api<V2Result>(`/api/v2/segment/${transcriptId}/result`);
}

export function useV2Result(transcriptId: number | null | undefined) {
  return useQuery<V2Result, Error>({
    queryKey: ['v2result', transcriptId],
    queryFn: () => fetchV2Result(transcriptId as number),
    enabled: typeof transcriptId === 'number' && transcriptId > 0,
    // авто-опросим, пока процесс идёт
    refetchInterval: (q) => {
      const d = q.state.data as V2Result | undefined;
      return d && (d.status === 'processing' || d.status === 'transcription_processing') ? 1500 : false;
    },
    staleTime: 500,
  });
}
