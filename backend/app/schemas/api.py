from typing import List, Optional, Literal
from pydantic import BaseModel, Field

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
class RecognizeRequest(BaseModel):
    file_id: int = Field(..., ge=1)
    meeting_id: int = Field(..., ge=1)


class RecognizeResponse(BaseModel):
    transcript_id: int
    status: str
    filename: str

# -----------------------------
# /diarization
# -----------------------------
class DiarizationRequest(BaseModel):
    file_id: int = Field(..., ge=1)
    meeting_id: int = Field(..., ge=1)


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
# /summary 
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
    text: str

# -----------------------------
# Статус транскрипции
# -----------------------------
class TranscriptStatus(BaseModel):
    status: str
    segments: Optional[List[SegmentInfo]] = None

class ProtokolResponse(BaseModel):
    transcript_id: int
    status: str
    filename: str


class ProtokolRequest(BaseModel):
    file_id: int = Field(..., ge=1)
    meeting_id: int = Field(..., ge=1)
    seg: Literal["diarize", "vad", "fixed"] = "diarize"

# --- Files API ---
class FileOut(BaseModel):
    id: int
    filename: str
    size_bytes: Optional[int] = None
    mimetype: Optional[str] = None
    created_at: Optional[str] = None  # ISO строка

class FilesListResponse(BaseModel):
    items: List[FileOut]
    total: int

# --- Transcripts API ---
class TranscriptCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    meeting_id: int = Field(..., ge=1)
    file_id: int = Field(..., ge=1)

class TranscriptCreateOut(BaseModel):
    transcript_id: int
    status: str = "processing"

# ---------- mitings ----------
class MeetingCreateIn(BaseModel):
    file_id: int = Field(..., ge=1)
    meeting_id: int = Field(..., ge=1)
    title: str | None = None

class MeetingCreateOut(BaseModel):
    id: int
    status: str = "queued"

class MeetingGetOut(BaseModel):
    id: int
    meeting_id: int
    file_id: int | None = None
    filename: str | None = None
    title: str | None = None
    status: str
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    text: str | None = None