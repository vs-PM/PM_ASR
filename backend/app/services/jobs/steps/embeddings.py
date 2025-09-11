from sqlalchemy import select
from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgSegment, MfgEmbedding
from app.services.pipeline.embeddings import embed_text

log = get_logger(__name__)

async def run(transcript_id: int) -> int:
    async with async_session() as s:
        segs = (await s.execute(
            select(MfgSegment).where(MfgSegment.transcript_id == transcript_id)
        )).scalars().all()

        created = 0
        for seg in segs:
            emb = await embed_text(seg.text)
            if emb:
                s.add(MfgEmbedding(segment_id=seg.id, embedding=emb))
                created += 1
        await s.commit()

    log.info("Embeddings: created %d vectors for tid=%s", created, transcript_id)
    return created
