import { useMutation, useQuery } from '@tanstack/react-query';
import { getSummary, startEmbedSum } from '@/lib/summary';
import type { SegmentMode } from '@/lib/segmentation';

type StartArgs = { id: number; mode: SegmentMode; lang?: string; format?: string };

export function useStartEmbedSum() {
  return useMutation({
    mutationFn: (p: StartArgs) => startEmbedSum(p.id, p.mode, p.lang ?? 'ru', p.format ?? 'md'),
  });
}


export function useSummary(
  transcriptId: number | null,
  mode: SegmentMode,
  enabled: boolean,
  poll: boolean = false
) {
  return useQuery({
    queryKey: ['summary', transcriptId, mode],
    queryFn: async () => {
      if (!transcriptId) return { status: 'idle', text: '' };
      return getSummary(transcriptId, mode);
    },
    enabled: Boolean(transcriptId) && enabled,
    refetchInterval: poll ? 1500 : false, 
    staleTime: 1_000,
  });
}