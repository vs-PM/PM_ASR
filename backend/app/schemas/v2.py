# app/schemas/v2.py
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

SegmentMode = Literal["full", "vad", "fixed", "diarize"]

class SegmentStartIn(BaseModel):
    id: int = Field(..., ge=1)
    file_id: int = Field(..., ge=1)
    mode: SegmentMode = "diarize"
    meeting_id: Optional[int] = None
    overwrite: bool = False

class SegmentStartOut(BaseModel):
    transcript_id: int
    status: str = "processing"
    mode: SegmentMode
    chunks: Optional[int] = None

class SegmentStateOut(BaseModel):
    transcript_id: int
    status: str
    chunks: int

class TranscriptionStartOut(BaseModel):
    transcript_id: int
    status: str = "transcription_processing"

# --- result models ---

class SpeakerItem(BaseModel):
    id: int
    speaker: str
    display_name: Optional[str] = None
    color: Optional[str] = None
    is_active: bool = True

class DiarItem(BaseModel):
    id: int
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    speaker: Optional[str] = None

class SegmentTextItem(BaseModel):
    id: int
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    text: str
    speaker: Optional[str] = None
    lang: Optional[str] = None

class TranscriptV2Result(BaseModel):
    transcript_id: int
    status: str
    filename: Optional[str] = None
    file_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # текст, когда готов
    text: Optional[str] = None

    # после нарезки
    diarization: List[DiarItem] = []
    speakers: List[SpeakerItem] = []

    # опционально: текстовые сегменты (если в БД есть таблица/данные)
    segments: List[SegmentTextItem] = []
