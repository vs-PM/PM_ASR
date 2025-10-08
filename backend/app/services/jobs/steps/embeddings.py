from __future__ import annotations

from sqlalchemy import select

from app.db.session import async_session
from app.db.models import MfgSegment, MfgEmbedding
from app.core.logger import get_logger
from app.services.pipeline.embeddings import embed_text

log = get_logger(__name__)


async def run(transcript_id: int, mode: str | None = None) -> int:
    async with async_session() as s:
        # Берём сегменты нужного transcript_id (и mode, если указан),
        # у которых ещё нет строки в mfg_embedding.
        q = (
            select(MfgSegment)
            .outerjoin(MfgEmbedding, MfgEmbedding.segment_id == MfgSegment.id)
            .where(MfgSegment.transcript_id == transcript_id)
            .where(MfgEmbedding.segment_id.is_(None))
        )
        if mode:
            q = q.where(MfgSegment.mode == mode)

        segs = (await s.execute(q)).scalars().all()

        created = 0
        for seg in segs:
            text = (seg.text or "").strip()
            if not text:
                continue

            emb = await embed_text(text)
            if emb is None:
                continue

            s.add(MfgEmbedding(segment_id=seg.id, embedding=emb))
            created += 1

        await s.commit()

    log.info(
        "Embeddings(%s): created %d vectors for tid=%s",
        mode or "ALL",
        created,
        transcript_id,
    )
    return created
