from typing import List, Optional
from pydantic import BaseModel

class RecognizeResponse(BaseModel):
    transcript_id: int
    status: str
    filename: str

class SegmentInfo(BaseModel):
    speaker: str
    start_ts: int
    end_ts: int
    text: str

class TranscriptStatus(BaseModel):
    status: str
    segments: Optional[List[SegmentInfo]] = None