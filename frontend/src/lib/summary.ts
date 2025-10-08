import { api } from './api';
import type { SegmentMode } from './segmentation';

type SummaryGetResponse = {
  transcript_id: number;
  status: string;
  text: string;
};

export async function startEmbedSum(
  transcriptId: number,
  mode: SegmentMode,
  lang: string = 'ru',
  format: string = 'md'
) {
  return api(`/api/v2/transcripts/${transcriptId}/embedsum`, {
    method: 'POST',
    body: { mode, lang, format },
  });
}


export async function getSummary(
  transcriptId: number,
  mode: SegmentMode
): Promise<SummaryGetResponse> {
  return api<SummaryGetResponse>(`/api/v1/summary/${transcriptId}?mode=${mode}`, {
    method: 'GET',
  });
}