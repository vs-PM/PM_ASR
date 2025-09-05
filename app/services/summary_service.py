# app/services/summary_service.py
from __future__ import annotations

import json
import re
import time
from datetime import date
from typing import List, Tuple, Iterable, Optional

import httpx
import asyncio
from httpx import Timeout
from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import (
    MfgSegment,
    MfgSummarySection,
    MfgActionItem,
)
from app.services.embeddings_service import embed_text
from app.logger import get_logger
from app.config import settings

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────
# Утилиты (строки/JSON/датировки)
# ─────────────────────────────────────────────────────────

def _shorten(s: Optional[str], n: int = 300) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")

def _clip(s: Optional[str], n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"

def _split_into_batches(segments: List[MfgSegment], limit_chars: int) -> List[List[MfgSegment]]:
    """Режем список сегментов на батчи по суммарной длине текста."""
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

_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

def _extract_json(s: str) -> str:
    """Пытаемся вытащить валидный JSON-объект из строки (fenced/сырое/почти-JSON)."""
    s = (s or "").strip()
    if s.startswith("{") and s.endswith("}"):
        return s

    # fenced ```json ... ```
    m = _JSON_FENCE.search(s)
    if m:
        inner = m.group(1).strip()
        if inner.startswith("{") and inner.endswith("}"):
            return inner

    # сбалансированный поиск по фигурным скобкам (учёт строк/экранирования)
    start = s.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        cand = s[start:i+1].strip()
                        if cand.startswith("{") and cand.endswith("}"):
                            return cand
        # если не закрыли — попробуем последний «почти JSON»
    # прошлый «грубый» способ — на самый крайний случай
    m2 = re.search(r"(\{.*\})", s, re.DOTALL)
    return m2.group(1).strip() if m2 else "{}"

def _safe_date(d: Optional[str]) -> Optional[date]:
    if not d or str(d).lower() == "null":
        return None
    try:
        y, m, dd = map(int, str(d).split("-"))
        return date(y, m, dd)
    except Exception:
        return None

def _pack_context(batch: List[MfgSegment]) -> str:
    """Линейный контекст (по времени) из сегментов."""
    lines: List[str] = []
    for s in batch:
        spk = s.speaker or "SPEECH"
        st = 0.0 if s.start_ts is None else float(s.start_ts)
        et = 0.0 if s.end_ts   is None else float(s.end_ts)
        lines.append(f"[{spk} {st:.2f}-{et:.2f}] {s.text or ''}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# Кандидаты задач: эвристика + RAG на «task intent»
# ─────────────────────────────────────────────────────────

_TASK_TRIGGERS = [
    r"\bнужно\b", r"\bнадо\b", r"\bсделать\b", r"\bпоручаю\b", r"\bответствен\w*\b",
    r"\bк следующ(ей|ему)\b", r"\bсрок\b", r"\bдедлайн\b", r"\bподготовить\b",
    r"\bпроверить\b", r"\bисправить\b", r"\bназначить встречу\b", r"\bсозвон\b",
    r"\bотправить\b", r"\bдописать\b", r"\bпротестировать\b", r"\bсогласовать\b",
]
_TASK_QUERY_EMBED = (
    "найти действия, задачи, поручения, решения, договоренности; указание исполнителя,"
    " сроков; приоритет; follow-up; договорились; принять; поручено"
)

def _regex_task_hits(segs: List[MfgSegment], limit: int = 50) -> List[MfgSegment]:
    pat = re.compile("|".join(_TASK_TRIGGERS), flags=re.IGNORECASE)
    hits = [s for s in segs if (s.text and pat.search(s.text))]
    # приоритезируем более информативные (длина текста) и более поздние (по времени)
    hits.sort(key=lambda s: (len(s.text or ""), s.start_ts or 0.0), reverse=True)
    return hits[:limit]

async def _rag_task_hits(session: AsyncSession, transcript_id: int, segs: List[MfgSegment], top_k: int = 15) -> List[MfgSegment]:
    """RAG по «запросу задач»: эмбеддим запрос и ищем похожие сегменты внутри того же transcript_id."""
    try:
        qv = await embed_text(_TASK_QUERY_EMBED)
        if not qv:
            return []
        pairs = await _similar_segments(session, transcript_id, qv, top_k)
        ids = [seg_id for seg_id, score in pairs if score >= max(0.15, settings.rag_min_score)]
        idset = set(ids)
        by_id = {int(s.id): s for s in segs}
        return [by_id[i] for i in ids if i in by_id]
    except Exception:
        log.exception("RAG task hits failed")
        return []

def _assemble_task_candidates(segs: List[MfgSegment]) -> List[dict]:
    """Готовим легковесные кандидаты задач для промпта (усекаем до настроечных лимитов)."""
    limit = getattr(settings, "task_candidates_limit", 30)
    snip  = getattr(settings, "task_candidate_snippet", 160)
    out: List[dict] = []
    for s in segs[:limit]:
        t = s.text or ""
        if len(t) > snip:
            t = t[:snip] + "…"
        out.append({
            "segment_id": int(s.id),
            "speaker": s.speaker,
            "start_ts": float(s.start_ts) if s.start_ts is not None else None,
            "end_ts": float(s.end_ts) if s.end_ts is not None else None,
            "text": t,
        })
    return out


# ─────────────────────────────────────────────────────────
# pgvector: сериализация и поиск ближайших сегментов
# ─────────────────────────────────────────────────────────

def _to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

async def _similar_segments(
    session: AsyncSession, transcript_id: int, query_vec: List[float], top_k: int
) -> List[Tuple[int, float]]:
    """Ищем похожие сегменты внутри одного transcript_id (pgvector <=>)."""
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
# Ollama /api/chat — потоковый режим + общий тайм-аут
# ─────────────────────────────────────────────────────────

async def _ollama_chat(
    messages: list[dict],
    *,
    options: Optional[dict] = None,
    model_override: Optional[str] = None,
    force_json: bool = False,
) -> str:
    """
    Отправляет chat-сообщения в Ollama. Всегда стримит (устойчивее),
    общий тайм-аут ограничиваем через asyncio.timeout(...).
    """
    url = f"{settings.ollama_url}/api/chat"
    connect_t = getattr(settings, "ollama_connect_timeout", 30)
    overall_t = getattr(settings, "ollama_chat_timeout", 600)

    # базовые опции (безопасные для большинства моделей)
    base_options = {
        "num_ctx": getattr(settings, "summarize_num_ctx", 8192) or 8192,
        "num_predict": min(1024, max(128, int((getattr(settings, "summarize_num_ctx", 8192) or 8192) / 2))),
        "temperature": 0.2,
        "top_p": 0.9,
    }
    if options:
        base_options.update(options)

    payload = {
        "model": model_override or settings.summarize_model,
        "messages": messages,
        "stream": True,
        "keep_alive": getattr(settings, "ollama_keep_alive", "30m"),
        "options": base_options,
    }

    if force_json:
        # Ollama понимает `format: "json"` и старается держать вывод валидным
        payload["format"] = "json"

    log.debug(
        "Ollama chat → model=%s url=%s timeouts(connect)=%s, msgs=%s, options=%s",
        payload["model"], url, connect_t,
        [{"role": m.get("role"), "len": len(m.get("content",""))} for m in messages],
        {k: payload["options"][k] for k in ("num_ctx","num_predict","temperature","top_p")}
    )

    timeout = Timeout(connect=connect_t, read=None, write=None, pool=None)
    t0 = time.monotonic()
    chunks = 0
    content = ""
    try:
        async with asyncio.timeout(overall_t):
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                        except Exception:
                            continue
                        msg = evt.get("message") or {}
                        delta = msg.get("content") or ""
                        if delta:
                            content += delta
                            chunks += 1
                        if evt.get("done"):
                            break
        log.debug(
            "Ollama chat ← %s chars in %.2fs (chunks=%s)",
            len(content), time.monotonic() - t0, chunks
        )
        if not content:
            log.warning("Ollama chat вернул пустой ответ")
        return content
    except asyncio.TimeoutError:
        log.error("Ollama chat: общий тайм-аут %.1fs истёк", overall_t)
        raise
    except httpx.HTTPError:
        log.exception("Ollama chat HTTP error")
        raise
    except Exception:
        log.exception("Ollama chat unexpected error")
        raise


# ─────────────────────────────────────────────────────────
# Подсказки/шаблоны
# ─────────────────────────────────────────────────────────

SYSTEM_TEMPLATE_RU = """Ты — секретарь деловой встречи. Пиши строго на русском языке.
Жёсткие правила:
- Ничего не выдумывай. Любой факт, вывод, решение или задача должны опираться на текст стенограммы или на выдержки REF[…].
- Соблюдай хронологию. Секции — это логические этапы разговора по времени.
- В именах используй SPEAKER_xx или реальные имена, если они есть в тексте.
- РЕШЕНИЯ помечай «РЕШЕНО: …», риски — «РИСК: …», блокеры — «БЛОКЕР: …».
- Задачи (action items) формируй только при наличии явных формулировок («нужно/надо/сделать/поручаю/к следующему/срок/подготовить/проверить/согласовать» и т.п.). Если исполнителя/срока нет — ставь null.
- Если данных нет — оставляй поля пустыми/null. Не додумывай.
- Стиль: деловой, лаконичный, без воды."""

SYSTEM_TEMPLATE_EN = """You are a meeting secretary. Write strictly in English.
Rules:
- Ground every statement in transcript text or REF snippets; do not invent.
- Keep strict chronology; sections are time-ordered.
- Use SPEAKER_xx or real names if present.
- Mark decisions as DECISION:, risks as RISK:, blockers as BLOCKER:.
- Create action items only when explicit cues exist; leave assignee/due null if missing.
- If uncertain, leave fields empty; do not guess.
- Tone: concise, business-like."""

FINAL_JSON_SCHEMA_RU = """Верни ТОЛЬКО валидный JSON строго по схеме:
{
  "topic": "string",
  "summary_bullets": ["string", ...],
  "sections": [
    {
      "title": "string",
      "text": "string",
      "start_ts": 0.0,
      "end_ts": 0.0,
      "evidence_segment_ids": [int, ...]
    }
  ],
  "action_items": [
    {
      "assignee": "string|null",
      "due": "YYYY-MM-DD|null",
      "task": "string",
      "priority": "string|null",
      "source_segment_ids": [int, ...]
    }
  ]
}
Требования:
- Язык: русский.
- Таймкоды секций вычисляй как min/max по их evidence_segment_ids.
- В action_items включай только те задачи, у которых есть source_segment_ids (иначе не включай).
- Никаких комментариев вне JSON и без Markdown.
"""

def _system_prompt_for(lang: str) -> str:
    return SYSTEM_TEMPLATE_RU if (lang or "ru").lower().startswith("ru") else SYSTEM_TEMPLATE_EN

def _is_mostly_cyrillic(s: str) -> bool:
    if not s:
        return False
    cyr = sum(1 for ch in s if ("а" <= ch.lower() <= "я") or ch.lower() in "ёй")
    return cyr >= max(8, 0.3 * len(s))


# ─────────────────────────────────────────────────────────
# Глобальные RAG-выдержки с покрытием по времени
# ─────────────────────────────────────────────────────────

def _build_global_refs(
    segs: List[MfgSegment],
    pairs: Iterable[Tuple[int, float]],
    *,
    max_chars: int = 2000,
    bins: int = 8,
    per_bin: int = 3
) -> str:
    """
    Берём все (segment_id, score) из разных батчей, дедуплируем и строим
    хронологически покрывающий набор выдержек REF[…], чтобы финальная модель
    «видела» весь трек без огромного черновика.
    """
    # 1) дедуп с максимальным score
    by_id: dict[int, float] = {}
    for sid, sc in pairs:
        sid = int(sid)
        by_id[sid] = max(sc, by_id.get(sid, 0.0))

    if not by_id:
        return ""

    id2seg = {int(s.id): s for s in segs}
    items: List[Tuple[MfgSegment, float]] = [
        (id2seg[sid], sc) for sid, sc in by_id.items() if sid in id2seg
    ]
    # 2) сортировка по времени
    items.sort(key=lambda t: (t[0].start_ts or 0.0))

    # 3) бинирование по времени
    total_end = max((s.end_ts or 0.0) for s, _ in items) if items else 0.0
    if total_end <= 0:
        total_end = (items[-1][0].end_ts or 0.0) if items else 1.0
    bins = max(1, int(bins))
    bin_size = total_end / bins if total_end > 0 else 1.0
    buckets: List[List[Tuple[MfgSegment, float]]] = [[] for _ in range(bins)]
    for s, sc in items:
        st = s.start_ts or 0.0
        b = max(0, min(int(st / bin_size), bins - 1))
        buckets[b].append((s, sc))

    # 4) отбор top-per_bin в каждом «окне времени»
    lines: List[str] = []
    for bucket in buckets:
        bucket.sort(key=lambda t: t[1], reverse=True)
        for s, sc in bucket[:max(1, int(per_bin))]:
            spk = s.speaker or "SPEECH"
            st = 0.0 if s.start_ts is None else float(s.start_ts)
            et = 0.0 if s.end_ts   is None else float(s.end_ts)
            lines.append(
                f"[REF id={int(s.id)} score={sc:.2f} {spk} {st:.2f}-{et:.2f}] {s.text or ''}"
            )

    txt = "\n".join(lines)
    return txt if len(txt) <= max_chars else txt[:max_chars] + "…"


# ─────────────────────────────────────────────────────────
# Публичный сервис: генерация протокола (итеративно + RAG)
# ─────────────────────────────────────────────────────────

async def generate_protocol(transcript_id: int, lang: str = "ru", output_format: str = "json") -> None:
    t_start = time.monotonic()
    log.info(
        "Summary start: tid=%s | model=%s | rag_limit=%s, top_k=%s, min_score=%.3f",
        transcript_id, settings.summarize_model,
        settings.rag_chunk_char_limit, settings.rag_top_k, settings.rag_min_score
    )

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
            raise RuntimeError("No segments to summarize")

        total_chars = sum(len((s.text or "")) for s in segs)
        batches = _split_into_batches(segs, settings.rag_chunk_char_limit)
        log.info(
            "Segments loaded: tid=%s | segments=%s | total_chars=%s | batches=%s",
            transcript_id, len(segs), total_chars, len(batches)
        )

        # статистика по эмбеддингам
        try:
            emb_count = (await session.execute(
                text("""
                    SELECT count(*)
                    FROM mfg_embedding e
                    JOIN mfg_segment s ON s.id=e.segment_id
                    WHERE s.transcript_id=:tid
                """),
                {"tid": transcript_id}
            )).scalar_one()
            log.info("tid=%s: embeddings available = %s", transcript_id, emb_count)
        except Exception:
            log.exception("Failed to count embeddings for tid=%s", transcript_id)

        system_prompt = _system_prompt_for(lang)
        summary_so_far = ""

        # накапливаем пары для глобальных RAG-выдержек
        all_ref_pairs: List[Tuple[int, float]] = []

        # ИТЕРАЦИИ ПО БАТЧАМ
        for i, batch in enumerate(batches, 1):
            batch_chars = sum(len((s.text or "")) for s in batch)
            log.debug(
                "Batch %s/%s: segments=%s, chars=%s, first=[%s: %s]",
                i, len(batches), len(batch), batch_chars,
                (batch[0].speaker if batch else "—"), _shorten(batch[0].text if batch else "")
            )

            core_text_full = _pack_context(batch)
            t_emb = time.monotonic()
            q_vec = await embed_text(core_text_full[:4000])  # короткое «окно»
            log.debug("Embed window: ok=%s (len=%s) in %.3fs",
                      bool(q_vec), len(core_text_full[:4000]), time.monotonic() - t_emb)

            refs_text = ""
            if q_vec:
                pairs = await _similar_segments(session, transcript_id, q_vec, settings.rag_top_k)
                # фильтруем по порогу и собираем
                pairs = [p for p in pairs if p[1] >= settings.rag_min_score]
                all_ref_pairs.extend(pairs)

                seg_map = {int(s.id): s for s in segs}
                ref_lines: List[str] = []
                for seg_id, score in pairs:
                    s = seg_map.get(int(seg_id))
                    if not s:
                        continue
                    spk = s.speaker or "SPEECH"
                    st = 0.0 if s.start_ts is None else float(s.start_ts)
                    et = 0.0 if s.end_ts   is None else float(s.end_ts)
                    ref_lines.append(
                        f"[REF id={int(s.id)} score={score:.2f} {spk} {st:.2f}-{et:.2f}] {s.text or ''}"
                    )
                refs_text = "\n".join(ref_lines)
                # ограничим размер выдержек на шаге
                refs_text = _clip(refs_text, getattr(settings, "max_refs_chars", 2000))
                if refs_text:
                    log.debug("RAG refs chars=%s", len(refs_text))

            # ограничим переносимый черновик
            draft_snippet = _clip(summary_so_far, getattr(settings, "max_draft_chars", 1500))

            # готовим запрос на обновление черновика
            refs_block = f"Доп. релевантные выдержки:\n{refs_text}\n\n" if refs_text else ""
            user_chunk = (
                f"Шаг {i}/{len(batches)}.\n"
                "Кратко обнови черновик протокола по новому контенту ниже. Не повторяй сказанное ранее.\n\n"
                "Текущий контекст (хронология):\n"
                f"{core_text_full}\n\n"
                f"{refs_block}"
                "Текущий черновик протокола:\n"
                f"{draft_snippet}\n"
            )

            updated = await _ollama_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_chunk},
                ],
                options={
                    "num_predict": getattr(settings, "summarize_num_predict_draft", 256),
                    "temperature": 0.2,
                },
                model_override=None,  # можно подхватить отдельную «быструю» модель для драфта, если нужно
            )
            log.debug("Batch %s/%s: draft_out=%s", i, len(batches), _shorten(updated, 200))
            if updated:
                summary_so_far = updated

        # Соберём кандидатов задач: regex + RAG
        regex_hits = _regex_task_hits(segs, limit=50)
        rag_hits = await _rag_task_hits(session, transcript_id, segs, top_k=20)
        # мерджим по id с сохранением порядка: сначала regex, потом RAG-добавка
        seen: set[int] = set()
        merged_hits: List[MfgSegment] = []
        for s in regex_hits + rag_hits:
            sid = int(s.id)
            if sid not in seen:
                merged_hits.append(s)
                seen.add(sid)
        task_candidates = _assemble_task_candidates(merged_hits)
        log.info("Task candidates collected: %s", len(task_candidates))

        # Строим глобальные выдержки, чтобы финал опирался на всю хронологию
        global_refs = _build_global_refs(
            segs, all_ref_pairs,
            max_chars=getattr(settings, "max_refs_chars", 2000),
            bins=8, per_bin=3
        )

        # Сильно сжимаем черновик для финала
        summary_for_final = _clip(summary_so_far, getattr(settings, "max_draft_chars", 1500))

        # Финальный запрос: строгая JSON-структура, опора на Global REF + кандидаты задач
        final_req = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content":
                "Сформируй финальный протокол строго по схеме JSON ниже и на русском языке.\n\n"
                + FINAL_JSON_SCHEMA_RU
                + "\n\nГлобальные релевантные выдержки (покрывают всю хронологию):\n"
                + (global_refs or "")
                + "\n\nЧерновик (сжатый):\n"
                + (summary_for_final or "")
                + "\n\nКандидаты задач (усечённые; включай только подтверждённые текстом и добавляй source_segment_ids):\n"
                + json.dumps(task_candidates, ensure_ascii=False)
            }
        ]

        final_out = await _ollama_chat(
            final_req,
            options={
                "num_predict": getattr(settings, "summarize_num_predict_final", 512),
                "temperature": 0.2,
            },
            model_override=getattr(settings, "summarize_model_final", None),
            force_json=True,
        )
        js = _extract_json(final_out)
        log.debug("Final JSON head=%s", _shorten(js, 200))

        # Парсинг + ремонт при необходимости
        try:
            data = json.loads(js)
        except Exception:
            log.exception("Failed to parse model JSON. Storing minimal result.")
            repair_req = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content":
                    "Преобразуй следующий текст в СТРОГИЙ валидный JSON по схеме ниже. "
                    "Верни ТОЛЬКО JSON, без Markdown и комментариев.\n\n"
                    + FINAL_JSON_SCHEMA_RU
                    + "\n\nТекст для преобразования:\n"
                    + final_out[:20000]  # ограничим, чтобы не раздувать контекст
                }
            ]
            repaired = await _ollama_chat(
                repair_req,
                options={"num_predict": 512, "temperature": 0.1},
                model_override=getattr(settings, "summarize_model_final", None),
                force_json=True,  # <── просим strict json и тут
            )
            js2 = _extract_json(repaired)
            try:
                data = json.loads(js2)
            except Exception:
                log.exception("Failed to parse model JSON even after repair. Storing minimal result.")
                data = {"topic": "", "summary_bullets": [], "sections": [], "action_items": []}
                
        sections = data.get("sections") or []
        action_items = data.get("action_items") or []
        need_repair = any((not (sec.get("text") or "").strip()) for sec in sections)

        # Проверка языка задач (для RU)
        if (lang or "ru").startswith("ru"):
            non_ru_tasks = sum(1 for it in action_items if not _is_mostly_cyrillic(it.get("task","")))
            if non_ru_tasks > 0:
                need_repair = True

        if need_repair:
            log.info("Repair pass: filling empty section texts / normalizing tasks to RU")
            repair_payload = {
                "sections": sections,
                "action_items": action_items
            }
            repair_prompt = (
                "Отремонтируй JSON по тем же правилам и схеме.\n"
                "Заполни пустые 'text' у секций кратким содержанием на русском, сохрани хронологию.\n"
                "Если у секции нет evidence_segment_ids — подбери их из контекста (REF/черновик) и выставь start_ts/end_ts как min/max.\n"
                "Переведи action_items[].task на русский и оставь только те задачи, где можно указать source_segment_ids; иначе исключи.\n"
                "Верни ТОЛЬКО валидный JSON по той же схеме.\n\n"
                f"Текущий JSON:\n{json.dumps(repair_payload, ensure_ascii=False)}\n\n"
                f"Черновик:\n{summary_so_far}\n\n"
                f"Кандидаты задач:\n{json.dumps(task_candidates, ensure_ascii=False)}"
            )
            repaired = await _ollama_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": repair_prompt},
                ],
                options={"num_predict": 512, "temperature": 0.2},
                model_override=getattr(settings, "summarize_model_final", None),
            )
            js2 = _extract_json(repaired)
            try:
                data2 = json.loads(js2)
                sections = data2.get("sections") or sections
                action_items = data2.get("action_items") or action_items
                log.info("Repair applied: sections=%s, action_items=%s", len(sections), len(action_items))
            except Exception:
                log.warning("Repair parse failed; keep original output")

        # Fallback: если у секции нет start/end, но есть evidence_segment_ids — высчитаем
        if sections:
            id2seg = {int(s.id): s for s in segs}
            for sec in sections:
                if not sec.get("evidence_segment_ids"):
                    continue
                ev_ids = [int(x) for x in sec["evidence_segment_ids"] if isinstance(x, (int, str)) and str(x).isdigit()]
                times = [(id2seg[i].start_ts or 0.0, id2seg[i].end_ts or 0.0) for i in ev_ids if i in id2seg]
                if times:
                    st = min(t[0] for t in times)
                    et = max(t[1] for t in times)
                    sec["start_ts"] = float(st)
                    sec["end_ts"]   = float(et)

        # Сохранение в БД
        await session.execute(delete(MfgSummarySection).where(MfgSummarySection.transcript_id == transcript_id))
        await session.execute(delete(MfgActionItem).where(MfgActionItem.transcript_id == transcript_id))
        await session.commit()

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

        await session.commit()
        log.info(
            "Summary saved: tid=%s | sections=%s | action_items=%s | total=%.2fs",
            transcript_id, saved_sections, saved_items, time.monotonic() - t_start
        )
