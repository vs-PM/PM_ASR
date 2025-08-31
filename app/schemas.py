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
# Статус транскрипции
# -----------------------------
class TranscriptStatus(BaseModel):
    status: str
    segments: Optional[List[SegmentInfo]] = None
