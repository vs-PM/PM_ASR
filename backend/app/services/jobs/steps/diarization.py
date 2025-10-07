from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgDiarization
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.services.pipeline.diarization import diarize_file

log = get_logger(__name__)

async def run(transcript_id: int, audio_path: str) -> int:
    chunks = await diarize_file(audio_path)
    async with async_session() as s:
        if not chunks:
            return 0
        stmt = pg_insert(MfgDiarization).values([
            dict(
                transcript_id=transcript_id,
                speaker=c["speaker"],
                start_ts=c["start_ts"],
                end_ts=c["end_ts"],
                file_path=c["file_path"],
                mode="diarize",
            ) for c in chunks
        ])
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_mfg_diarization_chunk"
        )
        await s.execute(stmt)
        await s.commit()
    log.info("Diarization: upserted %d chunks for tid=%s", len(chunks), transcript_id)
    return len(chunks)