from __future__ import annotations
import asyncio
from typing import Optional, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from app.core.logger import get_logger
from app.core.security import decode_token
from app.db.session import async_session
from app.db.models import MfgJob, MfgJobEvent, MfgTranscript

log = get_logger(__name__)
router = APIRouter()  # внимание: этот роутер подключим БЕЗ /api/v1 префикса

async def _auth_ws(ws: WebSocket, token: Optional[str]) -> int:
    """
    Проверяем токен из query (?token=) или куку access_token (если один домен).
    Возвращаем user_id (или кидаем исключение для закрытия).
    """
    if token:
        payload = decode_token(token)
        typ = payload.get("typ")
        if typ not in {"ws", "access"}:
            raise ValueError("wrong typ")
        return int(payload["sub"])

    # cookie-путь (для prod/одного домена)
    cookie = ws.headers.get("cookie") or ws.headers.get("Cookie") or ""
    # очень простая выборка access_token=... из cookie
    for part in cookie.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "access_token" and v:
            payload = decode_token(v)
            if payload.get("typ") != "access":
                raise ValueError("wrong typ")
            return int(payload["sub"])

    raise ValueError("No token")

@router.websocket("/ws/jobs/{transcript_id}")
async def ws_jobs(ws: WebSocket, transcript_id: int, token: Optional[str] = Query(default=None)):
    try:
        # 1) auth
        user_id = await _auth_ws(ws, token)
        await ws.accept()
        log.info(f"WS connected user={user_id}, transcript_id={transcript_id}")

        # 2) отправим текущий статус/прогресс из mfg_job (если есть)
        last_event_id = 0
        async with async_session() as s:
            job = (await s.execute(
                select(MfgJob).where(MfgJob.transcript_id == transcript_id)
            )).scalar_one_or_none()

            if job:
                await ws.send_json({
                    "type": "status",
                    "status": job.status,
                    "step": job.step,
                    "progress": job.progress,
                    "message": job.error or "",
                })

            # дадим базовую информацию о транскрипте
            tr = (await s.execute(
                select(MfgTranscript).where(MfgTranscript.id == transcript_id)
            )).scalar_one_or_none()
            if tr:
                await ws.send_json({
                    "type": "transcript",
                    "id": tr.id,
                    "status": getattr(tr, "status", None),
                    "filename": getattr(tr, "filename", None),
                    "title": getattr(tr, "title", None),
                })

        # 3) простой “tail” по mfg_job_event: шлём все новые записи
        while True:
            await asyncio.sleep(1.0)
            async with async_session() as s:
                rows: List[MfgJobEvent] = (await s.execute(
                    select(MfgJobEvent).where(
                        MfgJobEvent.transcript_id == transcript_id,
                        MfgJobEvent.id > last_event_id
                    ).order_by(MfgJobEvent.id.asc())
                )).scalars().all()

                for ev in rows:
                    last_event_id = max(last_event_id, ev.id or 0)
                    # Нормализуем в унифицированный формат
                    payload = {
                        "type": "status",   # по вашим данным: status/progress/step/message
                        "status": ev.status,
                        "progress": ev.progress,
                        "step": ev.step,
                        "message": ev.message,
                        "ts": ev.created_at.isoformat() if ev.created_at else None,
                    }
                    await ws.send_json(payload)

    except WebSocketDisconnect:
        log.info("WS disconnected")
    except Exception as e:
        log.exception("WS error")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        await ws.close(code=4401)
