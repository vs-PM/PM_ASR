from app.core.logger import get_logger
from app.services.summary.service import generate_protocol

log = get_logger(__name__)

async def run(transcript_id: int, lang: str = "ru", fmt: str = "md") -> None:
    await generate_protocol(transcript_id, lang=lang, output_format=fmt)
    log.info("Summary generated for tid=%s", transcript_id)
