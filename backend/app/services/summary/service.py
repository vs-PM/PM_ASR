# app/services/summary/service.py
from __future__ import annotations

import time
from typing import List, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.db.models import MfgSegment, MfgSummarySection
from app.core.logger import get_logger
from app.core.config import settings

# ВАЖНО: правильный модуль с промптами
from .prompts import (
    system_prompt_for,
    render_batch_user_prompt,
    render_final_user_prompt,
)
from .rag import (
    split_into_batches,
    pack_context,
    similar_segments,
    build_global_refs,
)
from .client import ollama_chat
from app.services.pipeline.embeddings import embed_text

log = get_logger(__name__)


async def _upsert_summary(session: AsyncSession, transcript_id: int, draft: str, final_text: str) -> None:
    """
    Обновить/создать ровно одну строку в mfg_summary_section для данного transcript_id.
    title ← draft, text ← final.
    Храним в idx=1 (чтобы не получать дублей).
    """
    row = (
        await session.execute(
            select(MfgSummarySection)
            .where(
                MfgSummarySection.transcript_id == transcript_id,
                MfgSummarySection.idx == 1,
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    if row:
        row.title = draft or ""
        row.text = final_text or ""
        row.start_ts = None
        row.end_ts = None
    else:
        row = MfgSummarySection(
            transcript_id=transcript_id,
            idx=1,                    # <- ОБЯЗАТЕЛЬНО
            start_ts=None,
            end_ts=None,
            title=(draft or ""),
            text=(final_text or ""),
        )
        session.add(row)


async def generate_protocol(transcript_id: int, lang: str = "ru", output_format: str = "text") -> None:
    """
    Итеративная суммаризация (батчи + RAG) → финальный цельный текст протокола.
    Сохраняем: черновик в mfg_summary_section.title, финальный текст в mfg_summary_section.text (idx=1).
    """
    t_start = time.monotonic()
    log.info(
        "Summary start: tid=%s | model=%s | rag_limit=%s, top_k=%s, min_score=%.3f",
        transcript_id, settings.summarize_model,
        settings.rag_chunk_char_limit, settings.rag_top_k, settings.rag_min_score
    )

    # безопасные дефолты, если в .env пока нет этих параметров
    num_ctx = getattr(settings, "summarize_num_ctx", 8192)
    num_predict_batch = getattr(settings, "summarize_num_predict_batch", 256)
    num_predict_final = getattr(settings, "summarize_num_predict_final", 512)
    temperature = getattr(settings, "summarize_temperature", 0.2)

    async with async_session() as session:
        segs: List[MfgSegment] = (
            await session.execute(
                select(MfgSegment)
                .where(MfgSegment.transcript_id == transcript_id)
                .order_by(MfgSegment.start_ts)
            )
        ).scalars().all()

        if not segs:
            log.error("No segments to summarize for tid=%s", transcript_id)
            # Сохраняем пустую запись, чтобы статус не висел в processing
            await _upsert_summary(session, transcript_id, draft="", final_text="")
            await session.commit()
            return

        total_chars = sum(len((s.text or "")) for s in segs)
        batches = split_into_batches(segs, settings.rag_chunk_char_limit)
        log.info(
            "Segments loaded: tid=%s | segments=%s | total_chars=%s | batches=%s",
            transcript_id, len(segs), total_chars, len(batches)
        )

        system_prompt = system_prompt_for(lang)
        draft = ""

        # ——— итерации по батчам
        for i, batch in enumerate(batches, 1):
            core_text = pack_context(batch)

            # компактное окно для эмбеддинга → top-k ссылок
            t0 = time.monotonic()
            q_vec = await embed_text(core_text[:4000])
            dt = time.monotonic() - t0

            refs_text = ""
            if q_vec:
                pairs = await similar_segments(session, transcript_id, q_vec, settings.rag_top_k)
                pairs = [p for p in pairs if p[1] >= settings.rag_min_score]
                seg_map: Dict[int, MfgSegment] = {int(s.id): s for s in segs}
                ref_lines: List[str] = []
                for seg_id, score in pairs:
                    s = seg_map.get(int(seg_id))
                    if not s:
                        continue
                    ref_lines.append(
                        f"[REF id={seg_id} score={score:.2f} {s.speaker or 'UNK'} "
                        f"{float(s.start_ts or 0.0):.2f}-{float(s.end_ts or 0.0):.2f}] {s.text or ''}"
                    )
                refs_text = "\n".join(ref_lines)

            log.debug("Embed window: ok=%s (len=%s) in %.3fs", bool(q_vec), len(core_text[:4000]), dt)

            # ограниченный фрагмент черновика для подсказки модели
            max_draft = getattr(settings, "max_draft_chars", 8000)
            draft_snippet = draft[-max_draft:] if draft and len(draft) > max_draft else (draft or "")

            user_chunk = render_batch_user_prompt(
                step_idx=i,
                total_steps=len(batches),
                core_text=core_text,
                refs_text=refs_text,
                draft_snippet=draft_snippet,
                lang=lang,
            )

            updated = await ollama_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_chunk},
                ],
                options={
                    "num_ctx": num_ctx,
                    "num_predict": num_predict_batch,   # <- батчевый лимит
                    "temperature": temperature,
                },
            )

            if updated:
                draft = updated
            log.debug("Batch %s/%s: draft_len=%s", i, len(batches), len(draft))

        # ——— финальный проход
        global_refs = await build_global_refs(
            session, transcript_id, segs,
            max_refs_chars=getattr(settings, "max_refs_chars", 3000),
            top_k=max(10, settings.rag_top_k * 4),
        )

        draft_compact = draft[-getattr(settings, "max_final_draft_chars", 12000):] if draft else ""
        final_user_prompt = render_final_user_prompt(
            draft_compact=draft_compact,
            global_refs=global_refs or "",
            lang=lang,
        )

        final_text = await ollama_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_user_prompt},
            ],
            options={
                "num_ctx": num_ctx,
                "num_predict": num_predict_final,   # <- финальный лимит
                "temperature": temperature,
            },
        )

        if not (final_text and final_text.strip()):
            # на всякий случай, если финал пустой — оставим черновик
            final_text = draft or ""

        # ——— сохранить: title ← draft, text ← final_text (idx=1)
        await _upsert_summary(session, transcript_id, draft=draft or "", final_text=final_text or "")
        await session.commit()

        log.info("Summary saved: tid=%s | total=%.2fs", transcript_id, time.monotonic() - t_start)
