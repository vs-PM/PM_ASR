# app/services/summary/parsing.py
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────
# Вспомогательные утилиты
# ─────────────────────────────────────────────────────────

def shorten(s: str | None, n: int = 300) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")

def safe_date(d: str | None) -> Optional[date]:
    if not d or str(d).lower() == "null":
        return None
    try:
        y, m, dd = map(int, str(d).strip()[:10].split("-"))
        return date(y, m, dd)
    except Exception:
        return None

def is_mostly_cyrillic(s: str) -> bool:
    if not s:
        return False
    cyr = sum(1 for ch in s if ("а" <= ch.lower() <= "я") or ch.lower() in "ёй")
    return cyr >= max(8, 0.3 * len(s))

# ─────────────────────────────────────────────────────────
# Нормализация «почти правильного» Markdown
# ─────────────────────────────────────────────────────────

_HEADING_FIX = re.compile(r"^\s*#{2,}\s*(TOPIC|HIGHLIGHTS|SECTIONS|ACTION ITEMS)\s*$", re.IGNORECASE | re.MULTILINE)
_NUM_LIST = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_SEC_HEADER_ANY = re.compile(r"^\s*#{3,6}\s*\[\s*SEC\s*(\d+)\s*\]\s*(.+)$", re.IGNORECASE)
_EQ_OR_COLON = re.compile(r"\s*[:=]\s*")
_DECIMAL_COMMA = re.compile(r"(?P<num>\d+),(?P<frac>\d+)")
_SPACES_IN_SOURCES = re.compile(r"\s*,\s*")
_SOURCES_FIELD = re.compile(r"(sources)\s*[:=]\s*(?P<val>[^\n|]+)", re.IGNORECASE)
_START_FIELD = re.compile(r"(start)\s*[:=]\s*(?P<val>[^\n|]+)", re.IGNORECASE)
_END_FIELD   = re.compile(r"(end)\s*[:=]\s*(?P<val>[^\n|]+)", re.IGNORECASE)

def _to_float(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.strip()
    # убрать суффиксы вроде "сек", "s"
    s = re.sub(r"\s*(сек|seconds?|s)\b\.?$", "", s, flags=re.IGNORECASE)
    # запятая как десятичный разделитель
    s = _DECIMAL_COMMA.sub(r"\g<num>.\g<frac>", s)
    try:
        return float(s)
    except Exception:
        return None

def _parse_sources_val(val: str) -> List[int]:
    val = (val or "").strip()
    val = _SPACES_IN_SOURCES.sub(",", val)  # "1, 2, 3" → "1,2,3"
    parts = [p.strip() for p in re.split(r"[;,]", val) if p.strip()]
    out: List[int] = []
    for p in parts:
        if p.isdigit():
            out.append(int(p))
        else:
            m = re.search(r"(\d+)", p)
            if m:
                out.append(int(m.group(1)))
    return out

def normalize_controlled_md(md: str) -> str:
    """
    Приводит заголовки к "#", пункты HIGHLIGHTS к "-", унифицирует секции и поля.
    Делает парсер устойчивым к "### TOPIC", нумерованным спискам, start: / end:, пробелам в sources, десятичной запятой и т.п.
    """
    if not md:
        return ""

    lines = md.strip().splitlines()

    # 1) Заголовки: ### TOPIC → # TOPIC (и т.п.)
    text = "\n".join(lines)
    text = _HEADING_FIX.sub(lambda m: f"# {m.group(1).upper()}", text)

    # 2) HIGHLIGHTS: "1. ..." → "- ..."
    text = text.replace("# HIGHLIGHTS", "# HIGHLIGHTS")
    # только внутри блока HIGHLIGHTS заменим нумерацию на дефис
    parts = re.split(r"(^\# (?:TOPIC|HIGHLIGHTS|SECTIONS|ACTION ITEMS)\s*$)", text, flags=re.MULTILINE)
    if len(parts) > 1:
        rebuilt: List[str] = []
        i = 0
        while i < len(parts):
            if re.match(r"^\# HIGHLIGHTS\s*$", parts[i], flags=re.IGNORECASE | re.MULTILINE):
                # заголовок + тело
                rebuilt.append(parts[i]); i += 1
                if i < len(parts):
                    body = _NUM_LIST.sub("- ", parts[i])
                    rebuilt.append(body); i += 1
            else:
                rebuilt.append(parts[i])
                i += 1
        text = "".join(rebuilt)

    # 3) Секции: допускаем ###/####, ":" или "=", пробелы/запятые в sources, запятую как дробную
    fixed_lines: List[str] = []
    for ln in text.splitlines():
        m = _SEC_HEADER_ANY.match(ln)
        if not m:
            fixed_lines.append(ln)
            continue

        sec_idx = m.group(1)
        rest = m.group(2).strip()

        # разрезаем по " | "
        parts = [p.strip() for p in rest.split("|")]
        if not parts:
            fixed_lines.append(ln)
            continue

        title = parts[0].strip()

        start_v = None
        end_v = None
        srcs: List[int] = []

        for p in parts[1:]:
            # нормализуем "start : 12,34 сек" → "start=12.34"
            p = _EQ_OR_COLON.sub("=", p)
            if p.lower().startswith("start="):
                start_v = _to_float(p.split("=", 1)[1])
            elif p.lower().startswith("end="):
                end_v = _to_float(p.split("=", 1)[1])
            elif p.lower().startswith("sources="):
                raw = p.split("=", 1)[1]
                srcs = _parse_sources_val(raw)

        # собираем унифицированную шапку
        head = f"#### [SEC {sec_idx}] {title}"
        head += f" | start={start_v if start_v is not None else 0.0}"
        head += f" | end={end_v if end_v is not None else 0.0}"
        head += f" | sources={','.join(str(x) for x in srcs)}"
        fixed_lines.append(head)

    return "\n".join(fixed_lines)

# ─────────────────────────────────────────────────────────
# Парсинг контролируемого Markdown → структура
# ─────────────────────────────────────────────────────────

# Уже нормализованный формат:
_SEC_RE = re.compile(
    r"^####\s*\[SEC\s+(?P<idx>\d+)\]\s*(?P<title>.*?)\s*\|\s*start=(?P<start>\d+(?:\.\d+)?)\s*\|\s*end=(?P<end>\d+(?:\.\d+)?)\s*\|\s*sources=(?P<sources>[^\n|]*)\s*$"
)

def parse_controlled_markdown(md: str) -> Dict[str, Any]:
    """
    Разбирает Markdown из CONTROLLED_MD_SPEC_RU (после normalize_controlled_md) в словарь:
    {
      "topic": str,
      "summary_bullets": [str, ...],
      "sections": [{"title","text","start_ts","end_ts","evidence_segment_ids"}],
      "action_items": [{"assignee","due","task","priority","source_segment_ids"}]
    }
    """
    md = normalize_controlled_md(md or "")

    # Разобьём на блоки по заголовкам верхнего уровня
    parts = re.split(r"^\# (TOPIC|HIGHLIGHTS|SECTIONS|ACTION ITEMS)\s*$",
                     md.strip(), flags=re.MULTILINE)
    blocks: Dict[str, str] = {}
    for i in range(1, len(parts), 2):
        name = parts[i].strip().upper()
        body = parts[i+1].strip() if i+1 < len(parts) else ""
        blocks[name] = body

    topic = (blocks.get("TOPIC") or "").strip()

    # HIGHLIGHTS: строки, начинающиеся с "- "
    bullets: List[str] = []
    hl = (blocks.get("HIGHLIGHTS") or "")
    for line in hl.splitlines():
        line = line.strip()
        if line.startswith("- "):
            bullets.append(line[2:].strip())

    # SECTIONS
    sections: List[dict] = []
    secs_raw = (blocks.get("SECTIONS") or "")
    current = None
    buf: List[str] = []

    def flush():
        nonlocal current, buf, sections
        if current:
            current["text"] = "\n".join(buf).strip()
            sections.append(current)
        current, buf = None, []

    for line in secs_raw.splitlines():
        m = _SEC_RE.match(line.strip())
        if m:
            flush()
            srcs = _parse_sources_val(m.group("sources"))
            start = float(m.group("start"))
            end = float(m.group("end"))
            current = {
                "title": m.group("title").strip(),
                "start_ts": start,
                "end_ts": end,
                "evidence_segment_ids": srcs,
                "text": ""
            }
        else:
            if current is not None:
                buf.append(line)
    flush()

    # ACTION ITEMS: разберём гибко: "- [TASK] <params> :: <text>"
    items: List[dict] = []
    acts = (blocks.get("ACTION ITEMS") or "")
    for line in acts.splitlines():
        raw = line.strip()
        if not raw:
            continue
        if not raw.startswith("- [TASK]"):
            continue

        # отделим правую часть (текст задачи) от левой (параметры)
        parts = raw.split("::", 1)
        params_part = parts[0][len("- [TASK]"):].strip()
        task_text = (parts[1] if len(parts) > 1 else "").strip()

        # параметры формата key[:=]value, через "|"
        assignee = None
        due = None
        priority = None
        sources: List[int] = []

        for chunk in params_part.split("|"):
            chunk = chunk.strip()
            if not chunk:
                continue
            kv = _EQ_OR_COLON.split(chunk, maxsplit=1)
            if len(kv) != 2:
                continue
            key = kv[0].strip().lower()
            val = kv[1].strip()
            if key == "assignee":
                assignee = None if val.lower() == "null" else val
            elif key == "due":
                due = None if val.lower() == "null" else val
            elif key == "priority":
                priority = None if val.lower() == "null" else val
            elif key == "sources":
                sources = _parse_sources_val(val)

        items.append({
            "assignee": assignee,
            "due": due,
            "priority": priority,
            "task": task_text,
            "source_segment_ids": sources
        })

    return {
        "topic": topic,
        "summary_bullets": bullets,
        "sections": sections,
        "action_items": items,
    }
