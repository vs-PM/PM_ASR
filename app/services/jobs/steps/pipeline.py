from app.core.logger import get_logger
from app.services.pipeline.compose import process_pipeline_segments

log = get_logger(__name__)

async def run(transcript_id: int) -> None:
    await process_pipeline_segments(transcript_id)
    log.info("Pipeline ASR done for tid=%s", transcript_id)
