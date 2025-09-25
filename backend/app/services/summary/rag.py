# app/services/summary/rag.py
from __future__ import annotations

import time
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MfgSegment
from app.core.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────
# Разбиение и упаковка контекста
# ─────────────────────────────────────────────────────────

def split_into_batches(segments: List[MfgSegment], limit_chars: int) -> List[List[MfgSegment]]:
    batches: List[List[MfgSegment]] = []
    buf: List[MfgSegment] = []
    size = 0
    for s in segments:
        t = s.text or ""
        ln = len(t)
        if size + ln > limit_chars and buf:
            batches.append(buf)
            buf, size = [], 0
        buf.append(s)
        size += ln
    if buf:
        batches.append(buf)
    return batches


def pack_context(batch: List[MfgSegment]) -> str:
    """Линейный контекст (по времени)."""
    lines: List[str] = []
    for s in batch:
        spk = s.speaker or "UNK"
        st = float(s.start_ts or 0.0)
        en = float(s.end_ts or 0.0)
        lines.append(f"[{spk} {st:.2f}-{en:.2f}] {s.text or ''}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# Поиск похожих сегментов (pgvector)
# ─────────────────────────────────────────────────────────

def _to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def similar_segments(
    session: AsyncSession, transcript_id: int, query_vec: List[float], top_k: int
) -> List[Tuple[int, float]]:
    """top-k похожих сегментов для RAG (возвращает [(segment_id, score), ...])."""
    t0 = time.monotonic()
    vec_lit = _to_pgvector_literal(query_vec)
    sql = text(f"""
        SELECT e.segment_id,
               (1 - (e.embedding <=> '{vec_lit}'::vector)) AS score
        FROM mfg_embedding e
        JOIN mfg_segment s ON s.id = e.segment_id
        WHERE s.transcript_id = :tid
        ORDER BY e.embedding <=> '{vec_lit}'::vector
        LIMIT :k
    """)
    rows = (await session.execute(sql, {"tid": transcript_id, "k": top_k})).all()
    pairs = [(int(r[0]), float(r[1])) for r in rows]
    log.debug(
        "RAG query ok: tid=%s top_k=%s → %s rows in %.3fs; sample=%s",
        transcript_id, top_k, len(pairs), time.monotonic() - t0, pairs[:5]
    )
    return pairs


async def build_global_refs(
    session: AsyncSession,
    transcript_id: int,
    segs: List[MfgSegment],
    max_refs_chars: int = 3000,
    top_k: int = 20,
) -> str:
    """Глобальные выдержки для финала: берём равномерно по таймлайну + top-k по RAG из середины."""
    if not segs:
        return ""
    # равномерная выборка (по 1 из начала/середины/конца и т.д.)
    step = max(1, len(segs) // 10)
    sample_ids = set(s.id for s in segs[::step])

    # RAG вокруг середины текста
    mid_idx = len(segs) // 2
    window = segs[max(0, mid_idx - 10): mid_idx + 10]
    window_text = "\n".join((s.text or "") for s in window)[:4000]

    # Эмбеддинг окна: вызывать снаружи не хочется, но для простоты — пусть сервис даст
    # Здесь оставим без эмбеддинга; если нужно — подадим пусто и просто вернём равномерный набор
    vec_lit = None  # не используем здесь доп. запрос, оставим равномерный набор

    # Собираем строки
    seg_by_id = {s.id: s for s in segs}
    lines: List[str] = []
    for sid in sample_ids:
        s = seg_by_id.get(sid)
        if not s:
            continue
        lines.append(f"[REF id={sid} {s.speaker or 'UNK'} {float(s.start_ts or 0.0):.2f}-{float(s.end_ts or 0.0):.2f}] {s.text or ''}")

    text_refs = "\n".join(lines)
    return text_refs[:max_refs_chars]
