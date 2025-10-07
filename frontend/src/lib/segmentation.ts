import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from './api';

/* ==============================
 * Types
 * ============================== */

export type SegmentMode = 'diarize' | 'vad' | 'fixed' | 'full';
export const ALL_MODES: SegmentMode[] = ['diarize', 'vad', 'fixed', 'full'];

export type ModeStateLite = { mode: SegmentMode; status: string; chunks: number };

export interface SegmentationState {
  transcript_id: number;
  status: string;
  chunks: number;
}

export interface StartSegmentationPayload {
  id: number;            // transcript_id
  file_id: number;
  mode: SegmentMode;
}

export interface StartSegmentationOut {
  transcript_id: number;
  status: string;
  mode: SegmentMode;
  chunks: number;
}

export interface StartTranscriptionFromSegmentsIn {
  transcript_id: number;
  mode: SegmentMode;
}

export interface StartTranscriptionFromSegmentsOut {
  transcript_id: number;
  status: string;
}

export interface V2DiarItem {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  speaker: string | null;
}

export interface V2Speaker {
  id: number;
  speaker: string;            // нормализуем до строки
  display_name: string | null;
  color: string | null;
  is_active: boolean;
}

export interface V2TextItem {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  text: string;
  speaker: string | null;
  lang: string | null;
}

export interface V2Result {
  transcript_id: number;
  status: string;
  filename: string | null;
  file_id: number | null;
  created_at: string | null;
  updated_at: string | null;
  text: string | null;
  diarization: V2DiarItem[];
  speakers: V2Speaker[];
  segments: V2TextItem[];
}

/* Raw server shapes (allow undefined) */

interface V2TextItemRaw {
  id?: number;
  start_ts?: number | null;
  end_ts?: number | null;
  text?: string;
  speaker?: string | null;
  lang?: string | null;
}

interface V2SpeakerRaw {
  id?: number;
  speaker?: string | null;
  display_name?: string | null;
  color?: string | null;
  is_active?: boolean;
}

interface V2ResultRaw {
  transcript_id?: number;
  status?: string;
  filename?: string | null;
  file_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  text?: string | null;
  diarization?: V2DiarItem[];
  speakers?: V2SpeakerRaw[];
  segments?: V2TextItemRaw[];
}

/* ==============================
 * API helpers
 * ============================== */

async function fetchSegmentationState(
  transcriptId: number,
  mode: SegmentMode
): Promise<SegmentationState> {
  return api<SegmentationState>(`/api/v2/segment/${transcriptId}?mode=${mode}`);
}

async function fetchAllModesState(transcriptId: number): Promise<ModeStateLite[]> {
  const modes = ALL_MODES;
  const results = await Promise.all(
    modes.map(async (m) => {
      try {
        const s = await fetchSegmentationState(transcriptId, m);
        return { mode: m, status: s.status, chunks: s.chunks } as ModeStateLite;
      } catch {
        return { mode: m, status: 'queued', chunks: 0 } as ModeStateLite;
      }
    })
  );
  return results;
}

async function startSegmentationV2(payload: StartSegmentationPayload): Promise<StartSegmentationOut> {
  return api<StartSegmentationOut>(`/api/v2/segment`, {
    method: 'POST',
    body: payload,
  });
}

async function startTranscriptionFromSegments(
  payload: StartTranscriptionFromSegmentsIn
): Promise<StartTranscriptionFromSegmentsOut> {
  const { transcript_id, mode } = payload;
  return api<StartTranscriptionFromSegmentsOut>(
    `/api/v2/segment/transcription/${transcript_id}?mode=${mode}`,
    { method: 'POST' }
  );
}

async function fetchV2Result(transcriptId: number, mode: SegmentMode): Promise<V2Result> {
  const r = await api<V2ResultRaw>(`/api/v2/segment/${transcriptId}/result?mode=${mode}`);

  const segments: V2TextItem[] = Array.isArray(r.segments)
    ? r.segments.map((s): V2TextItem => ({
        id: (s.id ?? 0) as number,
        start_ts: s.start_ts ?? null,
        end_ts: s.end_ts ?? null,
        text: s.text ?? '',
        speaker: s.speaker ?? null,
        lang: s.lang ?? null,
      }))
    : [];

  const speakers: V2Speaker[] = Array.isArray(r.speakers)
    ? r.speakers.map((s): V2Speaker => ({
        id: (s.id ?? 0) as number,
        speaker: s.speaker ?? '',
        display_name: s.display_name ?? null,
        color: s.color ?? null,
        is_active: s.is_active ?? true,
      }))
    : [];

  return {
    transcript_id: (r.transcript_id ?? transcriptId) as number,
    status: r.status ?? 'processing',
    filename: r.filename ?? null,
    file_id: r.file_id ?? null,
    created_at: r.created_at ?? null,
    updated_at: r.updated_at ?? null,
    text: r.text ?? null,
    diarization: Array.isArray(r.diarization) ? r.diarization : [],
    speakers,
    segments,
  };
}

/* ==============================
 * Hooks (no polling; keep data)
 * ============================== */

export function useAllModesState(transcriptId?: number) {
  return useQuery<ModeStateLite[], Error, ModeStateLite[]>({
    queryKey: ['segmentation-summary', transcriptId ?? 0] as const,
    queryFn: () => fetchAllModesState(transcriptId as number),
    enabled: Boolean(transcriptId),
    refetchInterval: false,
    placeholderData: (prev) => prev,
    staleTime: 0,
  });
}

export function useSegmentationState(transcriptId: number | undefined, mode: SegmentMode) {
  return useQuery<SegmentationState, Error, SegmentationState>({
    queryKey: ['segmentation-state', transcriptId ?? 0, mode] as const,
    queryFn: () => fetchSegmentationState(transcriptId as number, mode),
    enabled: Boolean(transcriptId),
    refetchInterval: false,
    placeholderData: (prev) => prev,
    staleTime: 0,
  });
}

export function useV2Result(transcriptId: number | undefined, mode: SegmentMode) {
  return useQuery<V2Result, Error, V2Result>({
    queryKey: ['v2-result', transcriptId ?? 0, mode] as const,
    queryFn: () => fetchV2Result(transcriptId as number, mode),
    enabled: Boolean(transcriptId),
    refetchInterval: false,
    placeholderData: (prev) => prev,
    staleTime: 0,
  });
}

/* ==============================
 * Mutations
 * ============================== */

export function useStartSegmentationV2() {
  return useMutation<StartSegmentationOut, Error, StartSegmentationPayload>({
    mutationFn: (body) => startSegmentationV2(body),
  });
}

export function useStartTranscriptionFromSegments() {
  return useMutation<StartTranscriptionFromSegmentsOut, Error, StartTranscriptionFromSegmentsIn>({
    mutationFn: (body) => startTranscriptionFromSegments(body),
  });
}
