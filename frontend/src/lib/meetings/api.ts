import { api } from '../api';
import {
  MeetingDetail,
  MeetingList,
  MeetingMeta,
  MeetingStatus,
  StartTranscriptionNormalized,
  Segmentation,
} from './types';

/** Метаданные митинга (без текста/сегментов) */
export async function fetchMeetingMeta(meetingId: number): Promise<MeetingMeta> {
  return api<MeetingMeta>(`/api/v1/meetings/${meetingId}`);
}

/** Деталь транскрипта; если 404 — «пустая» карточка по мета-данным */
export async function fetchMeeting(meetingId: number): Promise<MeetingDetail> {
  try {
    // Деталь транскрипта по PK
    const res = await api<MeetingDetail>(`/api/v1/transcripts/${meetingId}`);
    // Нормализуем возможное поле text -> processed_text
    const processed = res.processed_text ?? res.text ?? null;
    const raw = res.raw_text ?? null;
    return { ...res, processed_text: processed, raw_text: raw };
  } catch (e: unknown) {
    const msg = (e as { message?: string })?.message ?? '';
    const is404 = /404|not found|Transcript not found/i.test(msg);
    if (!is404) throw e;

    const meta = await fetchMeetingMeta(meetingId);
    return {
      id: meta.id,
      meeting_id: meta.id,
      title: meta.title ?? null,
      status: (meta.status as MeetingStatus) ?? 'queued',
      filename: meta.filename ?? null,
      file_id: meta.file_id ?? null,
      created_at: meta.created_at ?? null,
      updated_at: meta.updated_at ?? null,
      processed_text: null,
      raw_text: null,
      text: null,
      job: null,
      segments: [],
      speakers: [],
      diarization: [],
      error: null,
    };
  }
}

/** Бэк: GET /api/v1/transcripts?limit&offset → {items,total} */
export async function fetchMeetings(page = 1, pageSize = 10): Promise<MeetingList> {
  const limit = pageSize;
  const offset = (page - 1) * pageSize;
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return api<MeetingList>(`/api/v1/transcripts?${params.toString()}`);
}

/** Создание митинга */
export async function createMeetingReq(body: { file_id: number; meeting_id: number; title?: string | null }) {
  // Важно: на бэке у /meetings/ есть завершающий слэш — оставляем его
  return api<{ id: number; status: 'queued' }>(`/api/v1/meetings/`, {
    method: 'POST',
    body,
  });
}

/** Получить title для TranscriptCreateIn.title (min_length=1) */
async function resolveTitleForTranscript(meetingId: number): Promise<string> {
  try {
    const meta = await fetchMeetingMeta(meetingId);
    const t = (meta.title ?? '').trim();
    const fn = (meta.filename ?? '').trim();
    if (t.length > 0) return t;
    if (fn.length > 0) return fn;
  } catch {
    // ignore — используем fallback ниже
  }
  return `Meeting #${meetingId}`;
}

export async function runTranscription(
  meetingId: number,
  _seg?: Segmentation,
): Promise<StartTranscriptionNormalized> {
  void _seg;
  const title = await resolveTitleForTranscript(meetingId);
  // На текущем бэке meeting_id == file_id == id (контракт зафиксирован)
  const body = { title, meeting_id: meetingId, file_id: meetingId };

  const res = await api<unknown>(`/api/v1/transcripts/`, {
    method: 'POST',
    body,
  });
  return normalizeStartResponse(res);
}

function normalizeStartResponse(res: unknown): StartTranscriptionNormalized {
  if (typeof res === 'object' && res !== null) {
    const r = res as Record<string, unknown>;
    if (typeof r.transcript_id === 'number') {
      return {
        transcript_id: r.transcript_id,
        status: typeof r.status === 'string' ? r.status : 'processing',
      };
    }
    if (typeof r.id === 'number') {
      return {
        transcript_id: r.id,
        status: typeof r.status === 'string' ? r.status : 'processing',
      };
    }
  }
  throw new Error('Unexpected response from /api/v1/transcripts/');
}
