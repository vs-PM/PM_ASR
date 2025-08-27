import os
import aiofiles
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Request, Query
from app.schemas import RecognizeResponse, TranscriptStatus, SegmentInfo
from app.services.asr_service import transcribe_with_diarization
from app.services.embeddings import embed_text
from app.background import process_and_save
from app.database import get_pool
from app.logger import get_logger

router = APIRouter()
log = get_logger(__name__)

@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    meeting_id: int = Query(..., description="ID встречи, к которой относится транскрипция")
):
    """
    1. Сохраняем загруженный файл во временную папку.
    2. Создаём запись в БД «processing».
    3. Запускаем фоновой таск, который выполнит транскрипцию.
    """
    log.debug(f"Received file: {file.filename}")
    tmp_dir = "/tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file.filename)

    # --- 1. Запись файла ---
    try:
        async with aiofiles.open(tmp_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)
        log.debug(f"Saved to temp: {tmp_path}")
    except Exception as exc:
        log.exception("Failed to write temp file")
        raise HTTPException(status_code=500, detail="File upload failed")

    # --- 2. Создаём запись в БД ---
    try:
        # Используем уже инициализированный пул из app.state
        pool = request.app.state.pool  # FastAPI автоматически передаст объект request
        async with pool.acquire() as conn:
            rec = await conn.fetchrow(
                """
                INSERT INTO mfg_transcript (filename, status, meeting_id)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                file.filename,
                "processing",
                meeting_id,
            )
            record_id = rec["id"]
    except Exception as exc:
        log.exception("DB insert error")
        raise HTTPException(status_code=500, detail="Database error")

    log.info(f"Inserted transcript id={record_id} for file={file.filename}")

    # --- 3. Запускаем фоновой таск ---
    background_tasks.add_task(process_and_save, tmp_path, record_id)
    log.debug(f"Background task added for id={record_id}")

    return RecognizeResponse(
        status="processing",
        transcript_id=record_id,
        filename=file.filename
    )


@router.get("/status/{transcript_id}", response_model=TranscriptStatus)
async def status(transcript_id: int):
    """Возвращаем статус транскрипции + сегменты (если готово)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            transcript = await conn.fetchrow(
                """
                SELECT * FROM mfg_transcript WHERE id = $1
                """,
                transcript_id
            )
            if not transcript:
                raise HTTPException(status_code=404, detail="Transcript not found")

            if transcript["status"] != "done":
                return TranscriptStatus(status=transcript["status"])

            # Приготовим сегменты + embeddings
            segments = await conn.fetch(
                """
                SELECT * FROM mfg_segment
                WHERE transcript_id = $1
                ORDER BY start_ts
                """,
                transcript_id
            )
            return TranscriptStatus(
                status="done",
                segments=[
                    {"speaker": s["speaker"],
                     "start_ts": s["start_ts"],
                     "end_ts": s["end_ts"],
                     "text": s["text"]} for s in segments
                ]
            )
    except HTTPException as exc:
        raise
    except Exception as exc:
        log.exception("Ошибка при запросе статуса")
        raise HTTPException(status_code=500, detail="Database error")
