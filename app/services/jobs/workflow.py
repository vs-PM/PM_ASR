from __future__ import annotations

from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgTranscript
from app.services.jobs.types import JobContext, JobStatus
from app.services.jobs.progress import set_status
from app.services.jobs.locks import get_lock
from app.services.jobs.utils import clear_cuda_cache, safe_unlink
from app.services.jobs.steps import diarization, segmentation, pipeline, embeddings, summary

log = get_logger(__name__)

_DONE = {JobStatus.SUMM_DONE}
_ERROR = {JobStatus.ERROR}

async def _db_status(tid: int) -> str | None:
    async with async_session() as s:
        tr = await s.get(MfgTranscript, tid)
        return tr.status if tr else None

async def run_protokol(ctx: JobContext) -> None:
    lock = get_lock(ctx.transcript_id)
    if lock.locked():
        log.warning("Workflow already running: tid=%s", ctx.transcript_id)
        return

    async with lock:
        try:
            current = await _db_status(ctx.transcript_id)
            if current in _DONE:
                log.info("tid=%s already in final state: %s", ctx.transcript_id, current)
                return
            if current in _ERROR:
                log.warning("tid=%s in error — aborting", ctx.transcript_id)
                return

            # 1) Diarization/Segmentation (если еще не сделано)
            current = await _db_status(ctx.transcript_id)
            if current not in {JobStatus.DIAR_DONE.value, JobStatus.PIPE_DONE.value,
                               JobStatus.EMB_DONE.value, JobStatus.SUMM_DONE.value}:
                await set_status(ctx.transcript_id, JobStatus.DIAR_PROC)
                if ctx.seg_mode == "diarize":
                    await diarization.run(ctx.transcript_id, ctx.audio_path)
                else:
                    await segmentation.run(ctx.transcript_id, ctx.audio_path, ctx.seg_mode)
                await set_status(ctx.transcript_id, JobStatus.DIAR_DONE)

            # 2) Pipeline ASR (если еще не сделано)
            current = await _db_status(ctx.transcript_id)
            if current not in {JobStatus.PIPE_DONE.value, JobStatus.EMB_DONE.value, JobStatus.SUMM_DONE.value}:
                await set_status(ctx.transcript_id, JobStatus.PIPE_PROC)
                await pipeline.run(ctx.transcript_id)
                await set_status(ctx.transcript_id, JobStatus.PIPE_DONE)

            # 3) Embeddings (если еще не сделано)
            current = await _db_status(ctx.transcript_id)
            if current not in {JobStatus.EMB_DONE.value, JobStatus.SUMM_DONE.value}:
                await set_status(ctx.transcript_id, JobStatus.EMB_PROC)
                await embeddings.run(ctx.transcript_id)
                await set_status(ctx.transcript_id, JobStatus.EMB_DONE)

            # 4) Summary (если еще не сделано)
            current = await _db_status(ctx.transcript_id)
            if current not in {JobStatus.SUMM_DONE.value}:
                await set_status(ctx.transcript_id, JobStatus.SUMM_PROC)
                await summary.run(ctx.transcript_id, ctx.lang, ctx.fmt)
                await set_status(ctx.transcript_id, JobStatus.SUMM_DONE)

        except Exception:
            await set_status(ctx.transcript_id, JobStatus.ERROR)
            log.exception("Workflow failed: tid=%s", ctx.transcript_id)
        finally:
            # очищаем ресурсы в конце
            clear_cuda_cache()
            safe_unlink(ctx.audio_path)
