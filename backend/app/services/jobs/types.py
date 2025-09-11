from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Optional

class JobStatus(str, Enum):
    NEW = "new"
    DIAR_PROC = "diarization_processing"
    DIAR_DONE = "diarization_done"
    PIPE_PROC = "transcription_processing"
    PIPE_DONE = "transcription_done"
    EMB_PROC = "embeddings_processing"
    EMB_DONE = "embeddings_done"
    SUMM_PROC = "summary_processing"
    SUMM_DONE = "summary_done"
    ERROR = "error"

@dataclass
class JobContext:
    transcript_id: int
    audio_path: str
    lang: str = "ru"
    fmt: str = "json"
    seg_mode: str = "diarize"       # diarize | vad | fixed
    on_status: Optional[Callable[[JobStatus], Awaitable[None]]] = None
