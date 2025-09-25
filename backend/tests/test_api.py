from __future__ import annotations

from typing import Tuple

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api.v1 import health
from app.core.security import create_access_token
from app.db import models
from app.services.audit import audit_log


async def _create_transcript(
    session_maker,
    user_id: int,
    filename: str = "sample.wav",
    status: str = "ready",
) -> models.MfgTranscript:
    async with session_maker() as session:
        transcript = models.MfgTranscript(
            meeting_id=123,
            filename=filename,
            status=status,
            file_path="/tmp/sample.wav",
            user_id=user_id,
        )
        session.add(transcript)
        await session.commit()
        await session.refresh(transcript)
        return transcript


async def _create_file(session_maker, user_id: int) -> models.MfgFile:
    async with session_maker() as session:
        file_row = models.MfgFile(
            user_id=user_id,
            filename="audio.wav",
            stored_path="/tmp/audio.wav",
            size_bytes=3,
            mimetype="audio/wav",
        )
        session.add(file_row)
        await session.commit()
        await session.refresh(file_row)
        return file_row


def test_health_endpoints(client, monkeypatch):
    async def fake_ollama():
        return True, "ok"

    monkeypatch.setattr(health, "_check_ollama", fake_ollama)
    monkeypatch.setattr(health, "_check_ffmpeg", lambda: (True, "ffmpeg"))
    monkeypatch.setattr(health, "_check_cuda", lambda: {"available": False})

    resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["checks"]["ollama"]["ok"] is True

    ready = client.get("/api/v1/readyz")
    assert ready.status_code == 200
    assert ready.json()["db"]["ok"] is True

    live = client.get("/api/v1/livez")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"


def test_auth_flow(auth_client, seed_database: Tuple[models.MfgUser, models.MfgUser], monkeypatch):
    user, _ = seed_database

    login_resp = auth_client.post(
        "/api/v1/auth/login",
        json={"username": user.login, "password": "password"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json() == {"ok": True}
    refresh_cookie = login_resp.cookies.get("refresh_token")
    if refresh_cookie:
        auth_client.cookies.set(
            "refresh_token",
            refresh_cookie,
            domain="testserver",
            path="/api/v1/auth",
        )

    me_resp = auth_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["login"] == user.login

    ws_resp = auth_client.get("/api/v1/auth/ws-token")
    assert ws_resp.status_code == 200
    assert "token" in ws_resp.json()

    refresh_payload = {}
    if refresh_cookie:
        refresh_payload = {"refresh_token": refresh_cookie}
    refresh_resp = auth_client.post("/api/v1/auth/refresh", cookies=refresh_payload or None)
    assert refresh_resp.status_code in {200, 401}
    if refresh_resp.status_code == 200:
        assert refresh_resp.json() == {"ok": True}
    else:
        assert refresh_resp.status_code == 401

    logout_resp = auth_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"ok": True}

    # После logout повторный вызов /me должен вернуть 401
    me_after_logout = auth_client.get("/api/v1/auth/me")
    assert me_after_logout.status_code == 401


def test_files_endpoints(client):
    upload = client.post(
        "/api/v1/files/",
        files={"f": ("audio.wav", b"abc", "audio/wav")},
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    list_resp = client.get("/api/v1/files/")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == file_id

    detail = client.get(f"/api/v1/files/{file_id}")
    assert detail.status_code == 200
    assert detail.json()["filename"] == "audio.wav"


def test_transcription_upload_and_get(client, jobs_call_log):
    resp = client.post(
        "/transcription/",
        files={"file": ("meeting.wav", b"audio", "audio/wav")},
        params={"meeting_id": 42},
    )
    assert resp.status_code == 200
    transcript_id = resp.json()["transcript_id"]
    assert jobs_call_log["transcription"]

    status_resp = client.get(f"/transcription/{transcript_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "processing"


def test_diarization_upload(client, jobs_call_log):
    resp = client.post(
        "/diarization/",
        files={"file": ("meeting.wav", b"audio", "audio/wav")},
        params={"meeting_id": 99},
    )
    assert resp.status_code == 200
    assert jobs_call_log["diarization"]


def test_pipeline_endpoint(client, session_maker, run_async, seed_database, jobs_call_log):
    user, _ = seed_database
    transcript = run_async(_create_transcript(session_maker, user.id, status="ready"))

    resp = client.post(f"/pipeline/{transcript.id}")
    assert resp.status_code == 200
    assert jobs_call_log["pipeline"]

    async def fetch_status():
        async with session_maker() as session:
            refreshed = await session.get(models.MfgTranscript, transcript.id)
            return refreshed.status

    updated_status = run_async(fetch_status())
    assert updated_status == "transcription_processing"


def test_embeddings_endpoint(client, session_maker, run_async, seed_database, jobs_call_log):
    user, _ = seed_database
    transcript = run_async(_create_transcript(session_maker, user.id, status="ready"))

    resp = client.post(f"/embeddings/{transcript.id}")
    assert resp.status_code == 200
    assert jobs_call_log["embeddings"]

    async def fetch_status():
        async with session_maker() as session:
            refreshed = await session.get(models.MfgTranscript, transcript.id)
            return refreshed.status

    updated_status = run_async(fetch_status())
    assert updated_status == "embeddings_processing"


def test_summary_flow(client, session_maker, run_async, seed_database, jobs_call_log):
    user, _ = seed_database
    transcript = run_async(_create_transcript(session_maker, user.id, status="ready"))

    start = client.post(
        f"/summary/{transcript.id}",
        params={"lang": "ru", "format": "text"},
    )
    assert start.status_code == 200
    assert jobs_call_log["summary"]

    async def fetch_sections():
        async with session_maker() as session:
            result = await session.execute(
                select(models.MfgSummarySection).where(models.MfgSummarySection.transcript_id == transcript.id)
            )
            return result.scalars().all()

    sections = run_async(fetch_sections())
    assert any(section.idx == 0 for section in sections)

    get_resp = client.get(f"/summary/{transcript.id}")
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert payload["transcript_id"] == transcript.id
    assert payload["status"] in {"summary_processing", "summary_done"}


def test_protokol_endpoint(client, jobs_call_log):
    resp = client.post(
        "/protokol/",
        files={"file": ("meeting.wav", b"audio", "audio/wav")},
        params={"meeting_id": 55, "seg": "diarize"},
    )
    assert resp.status_code == 200
    assert jobs_call_log["protokol"]


def test_transcripts_crud(client, session_maker, run_async, seed_database, jobs_call_log):
    user, _ = seed_database
    file_row = run_async(_create_file(session_maker, user.id))

    create_resp = client.post(
        "/api/v1/transcripts/",
        json={"title": "Weekly Sync", "meeting_id": 777, "file_id": file_row.id},
    )
    assert create_resp.status_code == 201
    transcript_id = create_resp.json()["transcript_id"]
    assert jobs_call_log["transcription"]

    list_resp = client.get("/api/v1/transcripts/")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    detail = client.get(f"/api/v1/transcripts/{transcript_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == transcript_id

    rename = client.patch(f"/api/v1/transcripts/{transcript_id}", params={"title": "Updated"})
    assert rename.status_code == 200
    assert rename.json()["title"] == "Updated"


def test_admin_audit_endpoint(client, run_async):
    run_async(audit_log(user_id=1, action="login", object_type="user", object_id=1, meta={"source": "test"}))

    resp = client.get("/api/v1/admin/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["action"] == "login"


def test_ws_jobs_stream(client, session_maker, run_async, seed_database):
    user, _ = seed_database
    transcript = run_async(_create_transcript(session_maker, user.id, status="processing"))

    async def seed_job_data():
        async with session_maker() as session:
            job = models.MfgJob(
                transcript_id=transcript.id,
                status="processing",
                progress=10,
                step="queued",
            )
            session.add(job)
            session.add(
                models.MfgJobEvent(
                    transcript_id=transcript.id,
                    status="running",
                    progress=55,
                    step="asr",
                    message="job running",
                )
            )
            await session.commit()

    run_async(seed_job_data())

    token = create_access_token(user.id, user.role.value)

    with client.websocket_connect(f"/ws/jobs/{transcript.id}?token={token}") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()
        types = {first["type"], second["type"]}
        assert "status" in types
        assert "transcript" in types

        transcript_msg = first if first["type"] == "transcript" else second
        assert transcript_msg["id"] == transcript.id

        event_msg = websocket.receive_json()
        assert event_msg["type"] == "status"
        assert event_msg["step"] == "asr"
        assert event_msg["message"] == "job running"


def test_ws_jobs_requires_token(client, session_maker, run_async, seed_database):
    user, _ = seed_database
    transcript = run_async(_create_transcript(session_maker, user.id, status="processing"))

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/jobs/{transcript.id}"):
            pass

    assert exc.value.code == 4401

