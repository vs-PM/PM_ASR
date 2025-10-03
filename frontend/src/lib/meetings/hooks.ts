import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MEETINGS_PAGE_SIZE } from './constants';
import { meetingsKey } from './utils';
import { fetchMeeting, fetchMeetings, createMeetingReq, runTranscription } from './api';
import type { MeetingDetail, MeetingList, StartTranscriptionNormalized } from './types';

/** Деталь митинга/транскрипта */
export function useMeeting(meetingId: number) {
  return useQuery<MeetingDetail, Error>({
    queryKey: ['meeting', meetingId],
    queryFn: () => fetchMeeting(meetingId),
    /** Поллинг, пока процесс идёт */
    refetchInterval: (query) => {
      const d = query.state.data as MeetingDetail | undefined;
      const st = d?.status ?? d?.job?.status;
      return st && (st === 'processing' || st === 'transcription_processing') ? 1500 : false;
    },
    staleTime: 1_000,
  });
}

/** Список митингов */
export function useMeetings(page = 1, pageSize = MEETINGS_PAGE_SIZE) {
  return useQuery<MeetingList, Error>({
    queryKey: meetingsKey(page, pageSize),
    queryFn: () => fetchMeetings(page, pageSize),
    staleTime: 10_000,
  });
}

/** Инвалидация списка митингов */
export function useInvalidateMeetings() {
  const qc = useQueryClient();
  return (page?: number, pageSize = MEETINGS_PAGE_SIZE) =>
    qc.invalidateQueries({ queryKey: page ? meetingsKey(page, pageSize) : ['meetings'] });
}

/** Создание митинга */
export function useCreateMeeting() {
  const qc = useQueryClient();
  return useMutation<
    { id: number; status: 'queued' },
    Error,
    { file_id: number; meeting_id: number; title?: string | null }
  >({
    mutationFn: (payload) => createMeetingReq(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meetings'] });
      qc.invalidateQueries({ queryKey: ['files'] });
    },
  });
}

/** Запуск транскрипции (v1) */
export function useRunTranscription() {
  const qc = useQueryClient();
  return useMutation<StartTranscriptionNormalized, Error, { id: number }>({
    mutationFn: ({ id }) => runTranscription(id),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['meeting', vars.id] });
      qc.invalidateQueries({ queryKey: ['meetings'] });
    },
  });
}
