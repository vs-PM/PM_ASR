from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgDiarization
from app.services.pipeline.diarization import diarize_file

log = get_logger(__name__)

async def run(transcript_id: int, audio_path: str) -> int:
    chunks = await diarize_file(audio_path)
    async with async_session() as s:
        for c in chunks:
            s.add(MfgDiarization(
                transcript_id=transcript_id,
                speaker=c["speaker"],
                start_ts=c["start_ts"],
                end_ts=c["end_ts"],
                file_path=c["file_path"],
            ))
        await s.commit()
    log.info("Diarization: saved %d chunks for tid=%s", len(chunks), transcript_id)
    return len(chunks)
