import os
import aiofiles
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from app.models import RecognizeResponse, TranscriptStatus
from app.services.asr_service import transcribe_with_diarization
from app.services.embeddings import embed_text
from app.background import process_and_save
from app.database import get_pool

router = APIRouter()

@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(background_tasks: BackgroundTasks,
                    file: UploadFile = File(...)):
    tmp_dir = "/tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file.filename)

    async with aiofiles.open(tmp_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)

    # Создаём запись о транскрипции
    async with get_pool().__aenter__() as pool:
        async with pool.acquire() as conn:
            rec = await conn.fetchrow(
                "INSERT INTO transcripts (filename, status) VALUES ($1, $2) RETURNING id",
                file.filename, "processing"
            )
            record_id = rec["id"]

    background_tasks.add_task(process_and_save, tmp_path, record_id)
    return RecognizeResponse(status="processing", id=record_id, filename=file.filename)


@router.get("/status/{record_id}", response_model=TranscriptStatus)
async def status(record_id: int):
    async with get_pool().__aenter__() as pool:
        async with pool.acquire() as conn:
            rec = await conn.fetchrow(
                "SELECT status, raw_text FROM transcripts WHERE id = $1",
                record_id
            )
            if not rec:
                raise HTTPException(status_code=404, detail="Record not found")

            status = rec["status"]
            if status == "done":
                # Читаем сегменты
                segs = await conn.fetch(
                    """
                    SELECT speaker, start_ts, end_ts, text FROM segments
                    WHERE transcript_id = $1 ORDER BY start_ts
                    """,
                    record_id
                )
                segments = [
                    {"speaker": s["speaker"],
                     "start_ts": s["start_ts"],
                     "end_ts": s["end_ts"],
                     "text": s["text"]}
                    for s in segs
                ]
                return TranscriptStatus(status=status, segments=segments)
            else:
                return TranscriptStatus(status=status, text=None)