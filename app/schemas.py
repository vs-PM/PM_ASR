from typing import List, Optional
from pydantic import BaseModel

# -----------------------------
# Общие схемы
# -----------------------------
class SegmentInfo(BaseModel):
    speaker: str
    start_ts: float
    end_ts: float
    text: str

class ChunkInfo(BaseModel):
    speaker: str
    start_ts: float
    end_ts: float
    file_path: str

# -----------------------------
# /transcription
# -----------------------------
class RecognizeResponse(BaseModel):
    transcript_id: int
    status: str
    filename: str

# -----------------------------
# /diarization
# -----------------------------
class DiarizationResponse(BaseModel):
    transcript_id: int
    status: str
    filename: str
    chunks: Optional[List[ChunkInfo]] = None  # для будущего, можно оставить None при старте

# -----------------------------
# /pipeline
# -----------------------------
class PipelineResponse(BaseModel):
    transcript_id: int
    status: str

# -----------------------------
# /embeddings
# -----------------------------
class EmbeddingsResponse(BaseModel):
    transcript_id: int
    status: str


# -----------------------------
# /summary (Вариант B)
# -----------------------------
class SummaryStartResponse(BaseModel):
    transcript_id: int
    status: str  # processing

class SummarySection(BaseModel):
    idx: int
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    title: Optional[str] = None
    text: Optional[str] = None

class ActionItem(BaseModel):
    id: int
    assignee: Optional[str] = None
    due_date: Optional[str] = None  # ISO "YYYY-MM-DD" или None
    task: Optional[str] = None
    priority: Optional[str] = None

class SummaryGetResponse(BaseModel):
    transcript_id: int
    status: str
    sections: List[SummarySection]
    action_items: List[ActionItem]

# -----------------------------
# Статус транскрипции
# -----------------------------
class TranscriptStatus(BaseModel):
    status: str
    segments: Optional[List[SegmentInfo]] = None
