from app.services.asr_service import transcribe_file
from app.database import async_session
from app.models import MfgDiarization, MfgSegment, MfgTranscript
from app.logger import get_logger

log = get_logger(__name__)

async def process_pipeline_segments(transcript_id: int):
    """
    Для существующего transcript_id берём чанки из MfgDiarization,
    прогоняем через asr_service и сохраняем текст в MfgSegment.
    """
    async with async_session() as session:
        # Получаем все чанки
        chunks_res = await session.execute(
            MfgDiarization.__table__.select().where(MfgDiarization.transcript_id == transcript_id)
        )
        chunks = chunks_res.fetchall()
        log.info(f"Found {len(chunks)} chunks to transcribe for transcript {transcript_id}")

        for chunk in chunks:
            text = await transcribe_file(chunk.file_path)
            segment = MfgSegment(
                transcript_id=transcript_id,
                speaker=chunk.speaker,
                start_ts=chunk.start_ts,
                end_ts=chunk.end_ts,
                text=text
            )
            session.add(segment)

        transcript = await session.get(MfgTranscript, transcript_id)
        transcript.status = "transcription_done"
        session.add(transcript)
        await session.commit()
        log.info(f"Pipeline finished for transcript {transcript_id}")
