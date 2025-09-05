from __future__ import annotations
from typing import Dict, Optional

from app.db.session import async_session
from app.db.models import MfgTranscript
from app.services.jobs.types import JobStatus

# Простейший in-memory кэш статусов (не источник истины, но полезно для быстрых ответов)
_PROGRESS: Dict[int, JobStatus] = {}

async def set_status(tid: int, status: JobStatus) -> None:
    _PROGRESS[tid] = status
    async with async_session() as s:
        tr = await s.get(MfgTranscript, tid)
        if tr:
            tr.status = status.value
            s.add(tr)
            await s.commit()

def get_status(tid: int) -> Optional[JobStatus]:
    return _PROGRESS.get(tid)
