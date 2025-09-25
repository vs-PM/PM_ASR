from app.services.jobs.types import JobContext
from app.services.jobs.workflow import run_protokol
from app.services.jobs.steps.diarization import run as _run_diar
from app.services.jobs.steps.segmentation import run as _run_seg
from app.services.jobs.steps.pipeline import run as _run_pipe
from app.services.jobs.steps.embeddings import run as _run_emb
from app.services.jobs.steps.summary import run as _run_sum
from app.services.jobs.steps.transcription import run as _run_trans

# Сигнатуры оставлены как раньше в background.py

async def process_protokol(transcript_id: int, audio_path: str, lang: str = "ru",
                           format_: str = "json", seg_mode: str = "diarize") -> None:
    ctx = JobContext(transcript_id=transcript_id, audio_path=audio_path,
                     lang=lang, fmt=format_, seg_mode=seg_mode)
    await run_protokol(ctx)

async def process_diarization(transcript_id: int, audio_path: str) -> None:
    await _run_diar(transcript_id, audio_path)

async def process_segmentation(transcript_id: int, audio_path: str, mode: str = "vad") -> None:
    await _run_seg(transcript_id, audio_path, mode)

async def process_pipeline(transcript_id: int) -> None:
    await _run_pipe(transcript_id)

async def process_embeddings(transcript_id: int) -> None:
    await _run_emb(transcript_id)

async def process_summary(transcript_id: int, lang: str = "ru", format_: str = "md") -> None:
    await _run_sum(transcript_id, lang, format_)

async def process_transcription(transcript_id: int, audio_path: str) -> None:
    await _run_trans(transcript_id, audio_path)
