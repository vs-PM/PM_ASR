from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgTranscript
from app.services.pipeline.asr import transcribe_file

log = get_logger(__name__)

async def run(transcript_id: int, audio_path: str) -> int:
    """
    Полная транскрипция исходного файла (без диаризации/сегментации).
    Сохраняет текст в MfgTranscript.processed_text (если поле есть).
    Возвращает длину текста.
    """
    async with async_session() as s:
        tr = await s.get(MfgTranscript, transcript_id)
        if not tr:
            raise RuntimeError(f"Transcript {transcript_id} not found")

    text = await transcribe_file(audio_path)

    async with async_session() as s:
        tr = await s.get(MfgTranscript, transcript_id)
        # поле processed_text может называться иначе — скорректируй при необходимости
        if hasattr(tr, "processed_text"):
            setattr(tr, "processed_text", text)
        s.add(tr)
        await s.commit()

    log.info("Transcription (full-file) done: tid=%s, len=%s", transcript_id, len(text))
    return len(text)
