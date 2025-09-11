from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgDiarization
from app.services.pipeline.vad import segment_vad, segment_fixed

log = get_logger(__name__)

async def run(transcript_id: int, audio_path: str, mode: str = "vad") -> int:
    if mode == "vad":
        wav16k, chunks = await segment_vad(audio_path)
    else:
        wav16k, chunks = await segment_fixed(audio_path)

    async with async_session() as s:
        for c in chunks:
            s.add(MfgDiarization(
                transcript_id=transcript_id,
                speaker=c.get("speaker"),
                start_ts=c["start_ts"],
                end_ts=c["end_ts"],
                file_path=wav16k,
            ))
        await s.commit()
    log.info("Segmentation(%s): saved %d chunks for tid=%s", mode, len(chunks), transcript_id)
    return len(chunks)
