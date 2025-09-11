# app/services/summary/prompts.py
from __future__ import annotations

def system_prompt_for(lang: str) -> str:
    return SYSTEM_TEMPLATE_RU if (lang or "ru").lower().startswith("ru") else SYSTEM_TEMPLATE_EN


# ─────────────────────────────────────────────────────────
# Системные подсказки
# ─────────────────────────────────────────────────────────

SYSTEM_TEMPLATE_RU = """Ты — опытный ассистент руководителя проектов.
Твоя задача — превратить расшифровку встречи в чёткий, структурированный протокол.
Формат протокола:
- Участники
- Повестка дня (если явно озвучивалась — кратко; если нет, этот блок можно пропустить)
- Обсуждение (ключевые тезисы по темам; кратко, по сути)
- Принятые решения (по пунктам, однозначно)
- Задачи и следующие шаги (Action Items: исполнитель + срок, если есть; формулировать как действие)
Пиши строго на русском языке, деловым стилем. Не придумывай факты — опирайся на текст.
Если информации недостаточно, явно укажи «нет данных» или оставь пустым."""

SYSTEM_TEMPLATE_EN = """You are an experienced project assistant.
Turn the meeting transcript into structured minutes:
- Participants
- Agenda (if explicitly stated; otherwise omit)
- Discussion (key points by topic)
- Decisions (clear and concise)
- Action Items (assignee + due date if present; action-oriented)
Write in concise business English. Ground facts in the transcript; do not invent."""


# ─────────────────────────────────────────────────────────
# Промпты для батчей и финала
# ─────────────────────────────────────────────────────────

BATCH_USER_PROMPT_RU = """Продолжай формировать протокол встречи (шаг {step_idx}/{total_steps}).
Задача: кратко дополнить уже написанный черновик новыми фактами из контекста.
Не повторяй уже написанное, придерживайся структуры:
- Участники
- Повестка дня
- Обсуждение (по темам)
- Принятые решения
- Задачи и следующие шаги

Контекст (по хронологии):
{core_text}

Доп. релевантные выдержки (можно использовать точечно):
{refs_text}

Текущий черновик:
{draft_snippet}
"""

BATCH_USER_PROMPT_EN = """Continue composing the minutes (step {step_idx}/{total_steps}).
Task: enrich the existing draft with new facts from the context.
Do not repeat earlier content. Keep structure:
- Participants
- Agenda
- Discussion (by topics)
- Decisions
- Action Items

Context (chronological):
{core_text}

Extra relevant snippets:
{refs_text}

Current draft:
{draft_snippet}
"""

def render_batch_user_prompt(
    step_idx: int,
    total_steps: int,
    core_text: str,
    refs_text: str,
    draft_snippet: str,
    lang: str = "ru",
) -> str:
    tpl = BATCH_USER_PROMPT_RU if (lang or "ru").lower().startswith("ru") else BATCH_USER_PROMPT_EN
    return tpl.format(
        step_idx=step_idx,
        total_steps=total_steps,
        core_text=core_text.strip(),
        refs_text=(refs_text or "").strip() or "—",
        draft_snippet=(draft_snippet or "").strip() or "—",
    )


FINAL_USER_PROMPT_RU = """Сформируй цельный, полностью готовый протокол по всей встрече.
Критерии:
- Строгая структура: Участники; Повестка дня; Обсуждение (по темам); Принятые решения; Задачи и следующие шаги.
- Никаких таблиц; обычные подзаголовки и списки.
- Лаконичность, без воды, только факты из материала ниже.

Сжатый черновик (его можно переработать и улучшить):
{draft_compact}

Глобальные выдержки (вспомогательный материал, можно обращаться точечно):
{global_refs}

Верни ТОЛЬКО текст протокола (Markdown или чистый текст), без дополнительных комментариев.
"""

FINAL_USER_PROMPT_EN = """Produce a complete minutes document for the whole meeting.
Requirements:
- Structure strictly: Participants; Agenda; Discussion (by topics); Decisions; Action Items.
- No tables; simple headings and bullet points.
- Concise, factual, grounded in material below.

Compact draft (you may refine and improve it):
{draft_compact}

Global snippets (auxiliary material):
{global_refs}

Return ONLY the minutes text (Markdown or plain text), with no extra commentary."""

def render_final_user_prompt(
    draft_compact: str,
    global_refs: str,
    lang: str = "ru",
) -> str:
    tpl = FINAL_USER_PROMPT_RU if (lang or "ru").lower().startswith("ru") else FINAL_USER_PROMPT_EN
    return tpl.format(
        draft_compact=(draft_compact or "").strip(),
        global_refs=(global_refs or "").strip() or "—",
    )
