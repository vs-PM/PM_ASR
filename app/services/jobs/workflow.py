from __future__ import annotations

from app.core.logger import get_logger
from app.db.session import async_session
from app.db.models import MfgTranscript
from app.services.jobs.progress import set_status, set_progress
from app.services.jobs.locks import pg_advisory_lock
from app.services.jobs.utils import clear_cuda_cache, safe_unlink
from app.services.jobs.steps import diarization, segmentation, pipeline, embeddings, summary

log = get_logger(__name__)

FINAL = {"done"}
BAD   = {"error"}


async def _db_status(tid: int) -> str | None:
    async with async_session() as s:
        tr = await s.get(MfgTranscript, tid)
        return tr.status if tr else None


async def run_protokol(ctx: JobContext) -> None:
    async with pg_advisory_lock(ctx.transcript_id) as acquired:
        if not acquired:
            log.info("Skip run: lock not acquired (tid=%s)", ctx.transcript_id)
            return

        try:
            # 1) Сегментация
            if ctx.seg_mode == "diarize":
                await set_status(ctx.transcript_id, "processing", step="diarization")
                await set_progress(ctx.transcript_id, 10, step="diarization")
                await diarization.run(ctx.transcript_id, ctx.audio_path)
                await set_status(ctx.transcript_id, "diarization_done", step="diarization")
            else:
                await set_status(ctx.transcript_id, "processing", step="segmentation")
                await set_progress(ctx.transcript_id, 10, step="segmentation")
                await segmentation.run(ctx.transcript_id, ctx.audio_path, mode=ctx.seg_mode)
                # (опционально) фиксируем done по шагу
                await set_status(ctx.transcript_id, "segmentation_done", step="segmentation")

            # 2) Transcription (pipeline)
            await set_status(ctx.transcript_id, "processing", step="transcription")
            await set_progress(ctx.transcript_id, 45, step="transcription")
            stats = await pipeline.run(ctx.transcript_id, language=ctx.lang)
            log.info("Pipeline ASR done tid=%s stats=%s", ctx.transcript_id, stats)
            await set_status(ctx.transcript_id, "transcription_done", step="transcription")

            # 3) Embeddings
            await set_status(ctx.transcript_id, "processing", step="embeddings")
            await set_progress(ctx.transcript_id, 70, step="embeddings")
            await embeddings.run(ctx.transcript_id)
            await set_status(ctx.transcript_id, "embeddings_done", step="embeddings")

            # 4) Summary
            await set_status(ctx.transcript_id, "processing", step="summary")
            await set_progress(ctx.transcript_id, 90, step="summary")
            await summary.run(ctx.transcript_id, ctx.lang, ctx.fmt)

            # 5) Done (job-level)
            await set_progress(ctx.transcript_id, 100, step="summary")  # НЕ 'done'
            await set_status(ctx.transcript_id, "done", step="summary")  # выставит finished_at

        except Exception as e:
            # Терминальный статус + зафиксировать шаг как 'failed'
            await set_status(ctx.transcript_id, "error", step="failed", error=str(e))
            log.exception("Workflow failed tid=%s", ctx.transcript_id)
        finally:
            clear_cuda_cache()
            safe_unlink(ctx.audio_path)
