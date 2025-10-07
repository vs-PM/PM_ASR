import { useQuery } from '@tanstack/react-query';
import { fetchTranscriptV2ByMeeting } from './transcripts';
import type { MeetingDetail } from '../meetings/types';

export function useMeetingV2(meetingId: number, mode?: string) {
  return useQuery<MeetingDetail, Error>({
    queryKey: ['meeting-v2', meetingId, mode ?? null],
    queryFn: () => fetchTranscriptV2ByMeeting(meetingId, mode),
    refetchInterval: (query) => {
      const d = query.state.data as MeetingDetail | undefined;
      const st = d?.status ?? d?.job?.status;
      return st && (st === 'processing' || st === 'transcription_processing') ? 1500 : false;
    },
    staleTime: 1_000,
  });
}
