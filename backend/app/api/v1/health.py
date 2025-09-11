from __future__ import annotations
import time, platform, shutil, subprocess
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logger import get_logger
from app.core.config import settings
from app.db.session import async_engine

log = get_logger(__name__)
router = APIRouter()
_started_at = datetime.now(timezone.utc)
_started_monotonic = time.monotonic()

async def _check_db(engine: AsyncEngine) -> tuple[bool, str]:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:
        log.exception("DB health check failed")
        return False, f"error: {type(e).__name__}"

async def _check_ollama() -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            url = settings.ollama_url.rstrip("/") + "/api/tags"
            r = await client.get(url)
            if r.status_code == 200:
                return True, "ok"
            return False, f"http {r.status_code}"
    except Exception as e:
        return False, f"error: {type(e).__name__}"

def _check_ffmpeg() -> tuple[bool, str]:
    path = shutil.which("ffmpeg")
    if not path:
        return False, "not found"
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True)
        line = (out.stdout or out.stderr).splitlines()[0] if (out.stdout or out.stderr) else ""
        return True, line.strip() or "ok"
    except Exception as e:
        return False, f"error: {type(e).__name__}"

def _check_cuda() -> Dict[str, Any]:
    info: Dict[str, Any] = {"available": False}
    try:
        import torch
        info["available"] = bool(torch.cuda.is_available())
        try:
            info["cuda"] = getattr(torch.version, "cuda", None)
            info["cudnn"] = getattr(torch.backends.cudnn, "version", lambda: None)()
        except Exception:
            pass
    except Exception as e:
        info["error"] = f"torch import: {type(e).__name__}"
    return info

@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    db_ok, db_msg = await _check_db(async_engine)
    ollama_ok, ollama_msg = await _check_ollama()
    ff_ok, ff_msg = _check_ffmpeg()
    cuda = _check_cuda()
    return {
        "status": "ok" if (db_ok and ff_ok) else "degraded",
        "time": {
            "started_at": _started_at.isoformat(),
            "uptime_sec": round(time.monotonic() - _started_monotonic, 1),
        },
        "system": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": settings.device,
        },
        "checks": {
            "db": {"ok": db_ok, "msg": db_msg},
            "ollama": {"ok": ollama_ok, "msg": ollama_msg, "url": settings.ollama_url},
            "ffmpeg": {"ok": ff_ok, "msg": ff_msg},
            "cuda": cuda,
        },
    }

@router.get("/readyz")
async def readyz(resp: Response) -> Dict[str, Any]:
    db_ok, db_msg = await _check_db(async_engine)
    if not db_ok:
        resp.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"db": {"ok": db_ok, "msg": db_msg}}

@router.get("/livez")
async def livez() -> Dict[str, Any]:
    # процесс жив, без тяжёлых проверок
    return {"status": "alive", "uptime_sec": round(time.monotonic() - _started_monotonic, 1)}
