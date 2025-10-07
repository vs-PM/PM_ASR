// src/lib/v2/transcripts.ts
import { api } from '../api';
import type { MeetingDetail, MeetingStatus } from '../meetings/types';

/** Типы API v2 для точной типизации без any */

export interface ApiJob {
  status?: string;
  progress?: number | null;
  step?: string | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ApiSegmentItem {
  id?: number;
  start_ts?: number | null;
  end_ts?: number | null;
  text?: string;
  speaker?: string | null;
  lang?: string | null;
}

export interface ApiSpeakerItem {
  id?: number;
  speaker?: string | null;
  display_name?: string | null;
  color?: string | null;
  is_active?: boolean;
}

export interface ApiDiarItem {
  id?: number;
  start_ts?: number | null;
  end_ts?: number | null;
  speaker?: string | null;
}

export interface ApiTranscriptV2 {
  id?: number;
  meeting_id?: number;
  file_id?: number | null;
  title?: string | null;
  filename?: string | null;
  status?: string;
  created_at?: string | null;
  updated_at?: string | null;

  segments?: ApiSegmentItem[];
  speakers?: ApiSpeakerItem[];
  diarization?: ApiDiarItem[];

  job?: ApiJob;
  processed_text?: string | null;
  raw_text?: string | null;
}

/** v2: деталь по meeting_id с режимной фильтрацией (segments/diarization) */
export async function fetchTranscriptV2ByMeeting(meetingId: number, mode?: string): Promise<MeetingDetail> {
  const qs = new URLSearchParams();
  if (mode) qs.set('mode', mode);
  const r = await api<ApiTranscriptV2>(`/api/v2/transcripts/by-meeting/${meetingId}?${qs.toString()}`);

  const status: MeetingStatus = (r?.status as MeetingStatus) ?? 'processing';
  const progress = r?.job?.progress ?? null;

  return {
    id: r?.id ?? meetingId,
    meeting_id: r?.meeting_id ?? meetingId,
    file_id: r?.file_id ?? null,
    title: r?.title ?? null,
    filename: r?.filename ?? null,
    status,
    created_at: r?.created_at ?? null,
    updated_at: r?.updated_at ?? null,
    segments: Array.isArray(r?.segments) ? r.segments : [],
    speakers: Array.isArray(r?.speakers) ? r.speakers : [],
    diarization: Array.isArray(r?.diarization) ? r.diarization : [],
    job: r?.job
      ? {
          status: r.job.status ?? status,
          progress: progress,
          step: r.job.step ?? null,
          error: r.job.error ?? null,
          started_at: r.job.started_at ?? null,
          finished_at: r.job.finished_at ?? null,
        }
      : null,
    processed_text: r?.processed_text ?? null,
    raw_text: r?.raw_text ?? null,
  } as MeetingDetail;
}

/** v2: деталь по transcript_id (если понадобится в других экранах) */
export async function fetchTranscriptV2(transcriptId: number, mode?: string): Promise<MeetingDetail> {
  const qs = new URLSearchParams();
  if (mode) qs.set('mode', mode);
  const r = await api<ApiTranscriptV2>(`/api/v2/transcripts/${transcriptId}?${qs.toString()}`);

  const status: MeetingStatus = (r?.status as MeetingStatus) ?? 'processing';
  const progress = r?.job?.progress ?? null;

  return {
    id: r?.id ?? transcriptId,
    meeting_id: r?.meeting_id ?? r?.id ?? transcriptId,
    file_id: r?.file_id ?? null,
    title: r?.title ?? null,
    filename: r?.filename ?? null,
    status,
    created_at: r?.created_at ?? null,
    updated_at: r?.updated_at ?? null,
    segments: Array.isArray(r?.segments) ? r.segments : [],
    speakers: Array.isArray(r?.speakers) ? r.speakers : [],
    diarization: Array.isArray(r?.diarization) ? r.diarization : [],
    job: r?.job
      ? {
          status: r.job.status ?? status,
          progress: progress,
          step: r.job.step ?? null,
          error: r.job.error ?? null,
          started_at: r.job.started_at ?? null,
          finished_at: r.job.finished_at ?? null,
        }
      : null,
    processed_text: r?.processed_text ?? null,
    raw_text: r?.raw_text ?? null,
  } as MeetingDetail;
}

/** v2: запуск транскрипции от готовых сегментов по mode */
export async function runTranscriptionFromSegmentsV2(
  transcriptId: number,
  mode?: string
): Promise<{ transcript_id: number; status: string }> {
  const qs = new URLSearchParams();
  if (mode) qs.set('mode', mode);
  return api<{ transcript_id: number; status: string }>(
    `/api/v2/segment/transcription/${transcriptId}?${qs.toString()}`,
    { method: 'POST' }
  );
}
