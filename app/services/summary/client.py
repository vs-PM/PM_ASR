# app/services/summary/client.py
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

import httpx
from httpx import Timeout

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)


async def ollama_chat(messages: List[Dict], options: Optional[Dict] = None) -> str:
    """
    Вызов Ollama /api/chat с таймаутами из .env и стрим-фолбэком.
    Возвращает полный текст ответа (string). Если ответ пуст — вернёт "".
    """
    url = f"{settings.ollama_url}/api/chat"
    opts = {
        "num_ctx": settings.summarize_num_ctx,
    }
    if options:
        opts.update(options)

    payload = {
        "model": settings.summarize_model,
        "messages": messages,
        "options": opts,
        "stream": False,
        "keep_alive": getattr(settings, "ollama_keep_alive", "30m"),
    }

    # httpx.Timeout требует либо default, либо все 4 значения
    timeout = Timeout(
        connect=float(settings.ollama_connect_timeout or 30),
        read=None if (settings.ollama_read_timeout or 0) == 0 else float(settings.ollama_read_timeout),
        write=None if (settings.ollama_write_timeout or 0) == 0 else float(settings.ollama_write_timeout),
        pool=float(30),
    )

    # Логируем без содержимого текста, только длины
    safe_msgs = [{"role": m.get("role"), "len": len(m.get("content", ""))} for m in messages]
    log.debug(
        "Ollama chat → model=%s url=%s timeouts(connect/read/write/pool)=%.1f/%s/%s/%.1f, msgs=%s, options=%s",
        settings.summarize_model, url,
        float(settings.ollama_connect_timeout or 30),
        "∞" if (settings.ollama_read_timeout or 0) == 0 else str(float(settings.ollama_read_timeout)),
        "∞" if (settings.ollama_write_timeout or 0) == 0 else str(float(settings.ollama_write_timeout)),
        30.0,
        safe_msgs, opts
    )

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = (data.get("message") or {}).get("content", "") or ""
            if not content:
                log.warning("Ollama chat вернул пустой ответ")
            log.debug("Ollama chat ← %s chars in %.2fs", len(content), time.monotonic() - t0)
            return content
    except httpx.ReadTimeout:
        # Фолбэк на стрим — чтобы вытянуть частичный вывод
        log.warning("Ollama chat non-stream timeout — fallback to stream")
        payload["stream"] = True
        content = ""
        try:
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
                        chunk = (evt.get("message") or {}).get("content", "")
                        if chunk:
                            content += chunk
                        if evt.get("done"):
                            break
            log.debug("Ollama chat stream ← %s chars", len(content))
            return content
        except Exception:
            log.exception("Ollama chat stream fallback failed")
            return ""
    except Exception:
        log.exception("Ollama chat unexpected error")
        return ""
