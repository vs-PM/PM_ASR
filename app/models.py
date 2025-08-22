from pydantic import BaseModel, Field
from typing import Optional, List

class RecognizeResponse(BaseModel):
    status: str
    id: int
    filename: str

class Segment(BaseModel):
    speaker: str
    start_ts: float
    end_ts: float
    text: str

class TranscriptStatus(BaseModel):
    status: str
    text: Optional[str] = None
    segments: Optional[List[Segment]] = None