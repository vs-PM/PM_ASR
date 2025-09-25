# app/api/v1/files.py
from __future__ import annotations
from pathlib import Path
import uuid, os
from datetime import datetime

from fastapi.responses import FileResponse
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy import select, func
from app.core.auth import require_user
from app.db.session import async_session
from app.db.models import MfgFile
from app.core.logger import get_logger
from app.core.config import settings

log = get_logger(__name__)
router = APIRouter()

def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " .-_").strip() or "file"

@router.post("/", status_code=201)
async def upload_file(f: UploadFile = File(...), user=Depends(require_user)):
    now = datetime.utcnow()
    subdir = Path(settings.upload_dir) / f"{now.year:04d}" / f"{now.month:02d}"
    subdir.mkdir(parents=True, exist_ok=True)

    original = _safe_name(f.filename or "file")
    stored = f"{uuid.uuid4().hex}_{original}"
    dest = subdir / stored

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await f.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)

    async with async_session() as s:
        row = MfgFile(
            user_id=user.id,
            filename=original,
            stored_path=str(dest),
            size_bytes=size,
            mimetype=f.content_type or None,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return {
            "id": row.id,
            "filename": row.filename,
            "size_bytes": row.size_bytes,
            "mimetype": row.mimetype,
            "created_at": now.isoformat() + "Z",
        }

@router.get("/")
async def list_files(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(require_user),
):
    async with async_session() as s:
        total = (await s.execute(
            select(func.count(MfgFile.id)).where(MfgFile.user_id == user.id)
        )).scalar_one()
        rows = (await s.execute(
            select(MfgFile).where(MfgFile.user_id == user.id)
            .order_by(MfgFile.created_at.desc())
            .limit(limit).offset(offset)
        )).scalars().all()

        return {"items": [
            {
                "id": r.id, "filename": r.filename, "size_bytes": r.size_bytes,
                "mimetype": r.mimetype, "created_at": r.created_at
            } for r in rows
        ], "total": total}

@router.get("/{file_id}")
async def get_file(file_id: int, user=Depends(require_user)):
    async with async_session() as s:
        r = (await s.execute(
            select(MfgFile).where(MfgFile.id == file_id, MfgFile.user_id == user.id)
        )).scalar_one_or_none()
        if not r:
            raise HTTPException(404, "File not found")
        return {
            "id": r.id, "filename": r.filename, "size_bytes": r.size_bytes,
            "mimetype": r.mimetype, "created_at": r.created_at
        }


@router.get("/{file_id}/raw")
async def file_raw(file_id: int, user=Depends(require_user)):
    """
    Отдаёт сам аудиофайл. Требует авторизацию.
    Ответ: 200 OK (или 206 Partial Content при Range-запросе).
    Content-Disposition: inline; filename="<оригинальное имя>"
    """
    async with async_session() as s:
        r = (await s.execute(
            select(MfgFile).where(MfgFile.id == file_id, MfgFile.user_id == user.id)
        )).scalar_one_or_none()
        if not r:
            raise HTTPException(404, "File not found")

        # путь до сохранённого файла:
        # замените 'r.stored' на фактическое поле с относительным путём/именем хранения
        # пример: stored = "2025/09/25/uuid_original.wav"
        # в upload коде вы как раз формировали такое имя.
        stored_rel = getattr(r, "stored", None) or getattr(r, "stored_path", None)
        if not stored_rel:
            raise HTTPException(500, "Stored path is not set")

        file_path = Path(settings.upload_dir) / stored_rel
        if not file_path.is_file():
            raise HTTPException(404, "File content not found")

        # inline-отдача; FileResponse в Starlette поддерживает Range из коробки
        return FileResponse(
            path=file_path,
            media_type=r.mimetype or "application/octet-stream",
            filename=r.filename,  # оригинальное имя в заголовках
            headers={"Content-Disposition": f'inline; filename="{r.filename}"'}
        )
