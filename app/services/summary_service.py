# app/services/summary_service.py
from __future__ import annotations

import json
import re
import time
from datetime import date
from typing import List, Tuple

import httpx
from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import (
    MfgTranscript,
    MfgSegment,
    MfgSummarySection,
    MfgActionItem,
)
from app.services.embeddings_service import embed_text
from app.logger import get_logger
from app.config import settings

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────
# Утилиты
# ─────────────────────────────────────────────────────────

def _shorten(s: str | None, n: int = 300) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


def _split_into_batches(segments: List[MfgSegment], limit_chars: int) -> List[List[MfgSegment]]:
    """
    Бьём упорядоченные по времени сегменты на батчи по суммарной длине текста.
    """
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


def _extract_json(s: str) -> str:
    """
    Аккуратно достаём JSON-объект из свободной формы ответа модели.
    """
    s = (s or "").strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\{.*\})", s, re.DOTALL)
    return m.group(1).strip() if m else "{}"


def _safe_date(d: str | None) -> date | None:
    if not d or str(d).lower() == "null":
        return None
    try:
        y, m, dd = map(int, str(d).split("-"))
        return date(y, m, dd)
    except Exception:
        return None


def _pack_context(batch: List[MfgSegment]) -> str:
    lines: List[str] = []
    for s in batch:
        spk = s.speaker or "UNK"
        lines.append(f"[{spk} {s.start_ts:.2f}-{s.end_ts:.2f}] {s.text}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# pgvector: сериализация и поиск
# ─────────────────────────────────────────────────────────

def _to_pgvector_literal(vec: List[float]) -> str:
    """
    Сериализация списка чисел в pgvector-литерал: "[0.1,-0.2,...]".
    """
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def _similar_segments(
    session: AsyncSession, transcript_id: int, query_vec: List[float], top_k: int
) -> List[Tuple[int, float]]:
    """
    Семантический поиск по pgvector.
    ВАЖНО: инлайн-вектор в SQL (строковый литерал) + ::vector, чтобы обойти биндинг с asyncpg.
    Возвращает (segment_id, score) где score ~ 1 - cosine_distance.
    """
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


# ─────────────────────────────────────────────────────────
# Ollama /api/chat с фоллбеком на stream
# ─────────────────────────────────────────────────────────

async def _ollama_chat(messages: list[dict]) -> str:
    """
    Основной вызов Ollama /api/chat.
    1) Обычный запрос с расширенными таймаутами.
    2) При ReadTimeout — fallback на stream=True.
    """
    url = f"{settings.ollama_url}/api/chat"
    payload = {
        "model": settings.summarize_model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": getattr(settings, "summarize_num_ctx", 0) or 0,
        },
    }

    # берём таймауты из конфига и ЛОГИРУЕМ ИХ, а не атрибуты Timeout
    connect_t = getattr(settings, "ollama_connect_timeout", None) or 30
    read_t    = getattr(settings, "ollama_read_timeout", None) or getattr(settings, "ollama_chat_timeout", None) or 180
    write_t   = getattr(settings, "ollama_write_timeout", None) or 120

    timeout = httpx.Timeout(
        connect=connect_t,
        read=read_t,
        write=write_t,
        pool=None,
    )

    log.debug(
        "Ollama chat → model=%s url=%s timeouts(c/r/w)=%s/%s/%s, msgs=%s",
        settings.summarize_model, url, connect_t, read_t, write_t,
        [{"role": m.get("role"), "len": len(m.get("content",""))} for m in messages],
    )

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "") or ""
            log.debug("Ollama chat ← %s chars in %.2fs (non-stream)", len(content), time.monotonic() - t0)
            return content
    except httpx.ReadTimeout:
        log.warning(
            "Ollama chat non-stream timed out after %.2fs — falling back to stream mode",
            time.monotonic() - t0
        )
        # STREAM FALLBACK
        stream_payload = dict(payload)
        stream_payload["stream"] = True
        content = ""
        t1 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=stream_payload) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                        except Exception:
                            continue
                        msg = evt.get("message") or {}
                        chunk = msg.get("content", "")
                        if chunk:
                            content += chunk
                        if evt.get("done"):
                            break
            log.debug("Ollama chat ← %s chars in %.2fs (stream fallback)", len(content), time.monotonic() - t1)
            return content
        except Exception:
            log.exception("Ollama chat stream fallback failed")
            raise
    except Exception:
        log.exception("Ollama chat unexpected error (non-stream)")
        raise


# ─────────────────────────────────────────────────────────
# Подсказки для LLM
# ─────────────────────────────────────────────────────────

SYSTEM_TEMPLATE_RU = """Ты — секретарь совещаний. Из предоставленных фрагментов стенограммы ты ведёшь связный протокол встречи.
Требования:
- Всегда отвечай строго на русском языке.
- Сохраняй хронологию и причинно-следственные связи.
- Не выдумывай факты.
- Кратко перефразируй повторы.
- Отмечай решения (РЕШЕНО: …), задачи (ЗАДАЧА: исполнитель — срок — формулировка), риски.
- Сохраняй имена/идентификаторы спикеров как в тексте.
Работай итеративно: на каждом шаге получаешь новую порцию текста + релевантные выдержки (REF[…]). Обновляй “черновик протокола” без потери контекста.
В конце верни строго структурированный JSON по схеме ниже."""

FINAL_JSON_SCHEMA_RU = """Верни ТОЛЬКО валидный JSON со схемой:
{
  "sections": [
    {"title": "string", "text": "string", "start_ts": 0.0, "end_ts": 0.0}
  ],
  "action_items": [
    {"assignee": "string|null", "due": "YYYY-MM-DD|null", "task": "string", "priority": "string|null"}
  ]
}
Без комментариев вне JSON, без Markdown, без тройных кавычек.
Если нет данных — верни пустые списки.
"""


# ─────────────────────────────────────────────────────────
# Публичный сервис: генерация протокола 
# ─────────────────────────────────────────────────────────

async def generate_protocol(transcript_id: int, lang: str = "ru", output_format: str = "json") -> None:
    """
    Итеративная суммаризация батчами + RAG по эмбеддингам.
    Результат сохраняется в mfg_summary_section и mfg_action_item.
    """
    t_start = time.monotonic()
    log.info(
        "Summary start: tid=%s | model=%s | rag_limit=%s, top_k=%s, min_score=%.3f",
        transcript_id, settings.summarize_model,
        settings.rag_chunk_char_limit, settings.rag_top_k, settings.rag_min_score
    )

    async with async_session() as session:
        # 1) Сегменты (отсортированы по времени)
        segs = (
            await session.execute(
                select(MfgSegment)
                .where(MfgSegment.transcript_id == transcript_id)
                .order_by(MfgSegment.start_ts)
            )
        ).scalars().all()
        if not segs:
            log.error("No segments to summarize for tid=%s", transcript_id)
            raise RuntimeError("No segments to summarize")

        total_chars = sum(len((s.text or "")) for s in segs)
        batches = _split_into_batches(segs, settings.rag_chunk_char_limit)
        log.info(
            "Segments loaded: tid=%s | segments=%s | total_chars=%s | batches=%s",
            transcript_id, len(segs), total_chars, len(batches)
        )

        # лог: доступность эмбеддингов для информации
        try:
            emb_count = (await session.execute(
                text("""
                    SELECT count(*) 
                    FROM mfg_embedding e 
                    JOIN mfg_segment s ON s.id=e.segment_id 
                    WHERE s.transcript_id=:tid
                """), {"tid": transcript_id}
            )).scalar_one()
            log.info("tid=%s: embeddings available = %s", transcript_id, emb_count)
        except Exception:
            log.exception("Failed to count embeddings for tid=%s", transcript_id)

        system_prompt = SYSTEM_TEMPLATE_RU
        summary_so_far = ""

        # 2) Итеративные шаги
        for i, batch in enumerate(batches, 1):
            batch_chars = sum(len((s.text or "")) for s in batch)
            log.debug(
                "Batch %s/%s: segments=%s, chars=%s, first=[%s: %s]",
                i, len(batches), len(batch), batch_chars,
                (batch[0].speaker if batch else "—"),
                _shorten(batch[0].text if batch else "")
            )

            core_text = _pack_context(batch)
            refs_text = ""

            # 2.1) Эмбеддинг текущего окна
            t_emb = time.monotonic()
            q_vec = await embed_text(core_text[:4000])  # части достаточно
            log.debug(
                "Embed window: ok=%s in %.3fs (len=%s)",
                bool(q_vec), time.monotonic() - t_emb, len(core_text[:4000])
            )

            # 2.2) RAG-подбор релевантных сегментов
            if q_vec:
                pairs = await _similar_segments(session, transcript_id, q_vec, settings.rag_top_k)
                before = len(pairs)
                pairs = [p for p in pairs if p[1] >= settings.rag_min_score]
                log.debug(
                    "RAG filter: before=%s after=%s (min_score=%.3f), sample=%s",
                    before, len(pairs), settings.rag_min_score, pairs[:5]
                )
                if pairs:
                    seg_map = {s.id: s for s in segs}
                    ref_lines: List[str] = []
                    for seg_id, score in pairs:
                        s = seg_map.get(seg_id)
                        if not s:
                            continue
                        ref_lines.append(f"[REF {score:.2f} {s.speaker} {s.start_ts:.2f}-{s.end_ts:.2f}] {s.text}")
                    refs_text = "\n".join(ref_lines)
                    # ограничим размер RAG-выдержек
                    if refs_text and len(refs_text) > getattr(settings, "max_refs_chars", 2000):
                        refs_text = refs_text[:getattr(settings, "max_refs_chars", 2000)] + "…"
                    log.debug("RAG refs chars=%s", len(refs_text))

            # 2.3) Ограничим текущий черновик, чтобы не раздуть промпт
            draft_snippet = summary_so_far or ""
            max_draft = getattr(settings, "max_draft_chars", 6000)
            if len(draft_snippet) > max_draft:
                draft_snippet = "… " + draft_snippet[-max_draft:]

            # 2.4) Запрос к LLM (обновление черновика)
            refs_block = f"Доп. релевантные выдержки:\n{refs_text}\n\n" if refs_text else ""
            user_chunk = (
                f"Шаг {i}/{len(batches)}.\n"
                "Текущий контекст (хронология):\n"
                f"{core_text}\n\n"
                f"{refs_block}"
                "Текущий черновик протокола:\n"
                f"{draft_snippet}\n\n"
                "Задача: обнови черновик протокола с учётом новых данных. Не повторяй уже изложенное."
            )

            t_chat = time.monotonic()
            updated = await _ollama_chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_chunk},
            ])
            dt = time.monotonic() - t_chat
            log.debug(
                "Batch %s/%s: LLM updated draft in %.2fs | draft_out=%s",
                i, len(batches), dt, _shorten(updated, n=200)
            )
            summary_so_far = updated

        # 3) Финальная структуризация → JSON
        final_req = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Сформируй финальный итог по СХЕМЕ. " + FINAL_JSON_SCHEMA_RU + "\nВот черновик:\n" + (summary_so_far or "")}
        ]
        t_final = time.monotonic()
        final_out = await _ollama_chat(final_req)
        log.debug("Final LLM answer len=%s in %.2fs; head=%s",
                  len(final_out), time.monotonic() - t_final, _shorten(final_out, 200))
        js = _extract_json(final_out)
        log.debug("Extracted JSON len=%s; head=%s", len(js), _shorten(js, 200))

        try:
            data = json.loads(js)
        except Exception:
            log.exception("Failed to parse model JSON. Will store empty result. Raw_head=%s", _shorten(final_out, 300))
            data = {"sections": [], "action_items": []}

        sections = data.get("sections") or []
        action_items = data.get("action_items") or []
        log.info("Parsed result: sections=%s, action_items=%s", len(sections), len(action_items))

        # 4) Очистка предыдущего результата
        t_clean = time.monotonic()
        await session.execute(delete(MfgSummarySection).where(MfgSummarySection.transcript_id == transcript_id))
        await session.execute(delete(MfgActionItem).where(MfgActionItem.transcript_id == transcript_id))
        await session.commit()
        log.debug("Cleanup old summary: done in %.3fs", time.monotonic() - t_clean)

        # 5) Сохранение разделов
        saved_sections = 0
        for idx, sec in enumerate(sections, 1):
            try:
                session.add(MfgSummarySection(
                    transcript_id=transcript_id,
                    idx=idx,
                    start_ts=float(sec.get("start_ts")) if sec.get("start_ts") is not None else None,
                    end_ts=float(sec.get("end_ts")) if sec.get("end_ts") is not None else None,
                    title=(sec.get("title") or "").strip(),
                    text=(sec.get("text") or "").strip(),
                ))
                saved_sections += 1
            except Exception:
                log.exception("Failed to save section #%s: %s", idx, _shorten(str(sec), 300))

        # 6) Сохранение action items
        saved_items = 0
        for item in action_items:
            try:
                session.add(MfgActionItem(
                    transcript_id=transcript_id,
                    assignee=(item.get("assignee") or None),
                    due_date=_safe_date(item.get("due")),
                    task=(item.get("task") or "").strip(),
                    priority=(item.get("priority") or None),
                ))
                saved_items += 1
            except Exception:
                log.exception("Failed to save action item: %s", _shorten(str(item), 300))

        # 7) Обновляем статус транскрипта
        trs = await session.get(MfgTranscript, transcript_id)
        if trs:
            trs.status = "summary_done"
            session.add(trs)

        await session.commit()
        log.info(
            "Summary saved: tid=%s | sections=%s | action_items=%s | total=%.2fs",
            transcript_id, saved_sections, saved_items, time.monotonic() - t_start
        )
