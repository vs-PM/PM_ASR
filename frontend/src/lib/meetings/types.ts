/** Тип деления аудио (для совместимости с сигнатурами) */
export type Segmentation = 'none' | 'vad' | 'speaker' | 'fixed_30s';

/** Единый словарь статусов */
export type MeetingStatus =
  | 'queued'
  | 'processing'
  | 'diarization_done'
  | 'transcription_processing'
  | 'transcription_done'
  | 'embeddings_done'
  | 'done'
  | 'error';

/** Информация о фоновой job */
export type JobInfo = {
  status?: MeetingStatus | null;
  progress?: number | null;
  step?: string | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

/** Справочник спикеров */
export type SpeakerItem = {
  id: number;
  speaker: string;
  display_name: string | null;
  color: string | null;
  is_active: boolean;
};

/** Сегмент транскрипта */
export type SegmentItem = {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  text: string;
  speaker: string | null;
  lang: string | null;
};

/** Интервалы диаризации */
export type DiarItem = {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  speaker: string | null;
};

/** Детали митинга/транскрипта (для страницы деталей) */
export type MeetingDetail = {
  id: number;                 // PK транскрипта (совпадает с route [id])
  meeting_id: number;         // историческое поле (сейчас = id)
  title: string | null;
  status: MeetingStatus | null;
  filename: string | null;
  file_id: number | null;
  created_at: string | null;
  updated_at: string | null;

  processed_text?: string | null;
  raw_text?: string | null;
  /** Бэк может отдавать просто text — нормализуем в processed_text */
  text?: string | null;

  job?: JobInfo | null;

  segments?: SegmentItem[];
  speakers?: SpeakerItem[];
  diarization?: DiarItem[];

  error?: string | null;
};

/** Элемент списка митингов (список транскриптов) */
export type MeetingListItem = {
  id: number;
  meeting_id: number;
  file_id: number | null;
  filename: string | null;
  title: string | null;
  status: MeetingStatus | null;
  error?: string | null;
  created_at: string | null;
  updated_at: string | null;
  job?: {
    status?: MeetingStatus | null;
    progress?: number | null;
    step?: string | null;
    error?: string | null;
  } | null;
};

export type MeetingList = {
  items: MeetingListItem[];
  total: number;
};

export type MeetingMeta = {
  id: number;                // meeting_id (по сути = id)
  file_id: number | null;
  title?: string | null;
  filename?: string | null;
  status?: MeetingStatus | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type StartTranscriptionNormalized = {
  transcript_id: number;
  status: string;
};
