// src/lib/meetings.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';

export type Segmentation = 'none' | 'vad' | 'speaker' | 'fixed_30s';

export type MeetingStatus =
  | 'queued'
  | 'processing'
  | 'transcription_processing'
  | 'done'
  | 'error'
  | 'canceled'
  | null;

export type MeetingItem = {
  id: number;
  title?: string | null;
  filename?: string | null;
  file_id?: number | null;
  status?: MeetingStatus;
  created_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
};

export type MeetingList = { items: MeetingItem[]; total: number };

export type MeetingDetail = MeetingItem & {
  text?: string | null;
  result?: { text?: string | null; [k: string]: unknown } | null;
  segments?: Array<{ start: number; end: number; text: string }>;
};

export const MEETINGS_PAGE_SIZE = 20;

export function meetingsKey(page: number, pageSize = MEETINGS_PAGE_SIZE) {
  return ['meetings', page, pageSize] as const;
}

export async function fetchMeetings(page: number, pageSize = MEETINGS_PAGE_SIZE): Promise<MeetingList> {
  const offset = (page - 1) * pageSize;
  return api<MeetingList>(`/api/v1/transcripts/?limit=${pageSize}&offset=${offset}`);
}

export function useMeetings(page: number, pageSize = MEETINGS_PAGE_SIZE) {
  return useQuery<MeetingList, Error>({
    queryKey: meetingsKey(page, pageSize),
    queryFn: () => fetchMeetings(page, pageSize),
    staleTime: 10_000,
  });
}

export function useInvalidateMeetings() {
  const qc = useQueryClient();
  return (page?: number, pageSize = MEETINGS_PAGE_SIZE) =>
    qc.invalidateQueries({ queryKey: page ? meetingsKey(page, pageSize) : ['meetings'] });
}

export type CreateMeetingIn = { file_id: number; title?: string };
export type CreateMeetingOut = { id: number; status?: MeetingStatus };

export function useCreateMeeting() {
  const qc = useQueryClient();
  return useMutation<CreateMeetingOut, Error, CreateMeetingIn>({
    mutationFn: (body) => api<CreateMeetingOut>('/api/v1/transcripts/', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meetings'] }),
  });
}

export function useMeeting(id: number) {
  return useQuery<MeetingDetail, Error>({
    queryKey: ['meeting', id],
    queryFn: () => api<MeetingDetail>(`/api/v1/transcripts/${id}`),
    // авто-пуллинг только пока статус "processing"
    refetchInterval: (query) => {
      const d = query.state.data as MeetingDetail | undefined;
      const st = d?.status ?? null;
      return st === 'processing' || st === 'transcription_processing' ? 1500 : false;
    },
    staleTime: 1_000,
  });
}

export function runTranscription(id: number, seg?: Segmentation) {
  const qs = seg ? `?seg=${encodeURIComponent(seg)}` : '';
  return api<{ transcript_id: number; status: 'processing' }>(`/api/v1/pipeline/${id}${qs}`, {
    method: 'POST',
  });
}

export function useRunTranscription() {
  const qc = useQueryClient();
  return useMutation<{ transcript_id: number; status: 'processing' }, Error, { id: number; seg?: Segmentation }>({
    mutationFn: ({ id, seg }) => runTranscription(id, seg),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['meeting', vars.id] });
      qc.invalidateQueries({ queryKey: ['meetings'] });
    },
  });
}
