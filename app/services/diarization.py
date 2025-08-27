import torch
from asyncio import get_running_loop
from pyannote.audio import Pipeline
from pyannote.audio.pipelines import SpeakerDiarization
from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

MODEL_NAME = "pyannote/speaker-diarization"

def _load_pipeline() -> SpeakerDiarization:
    """
    Загружаем пайплайн один раз и возвращаем его.
    """
    device = torch.device(settings.device if torch.cuda.is_available() else "cpu")
    log.info(f"Loading pipeline {MODEL_NAME} on {device}")

    try:
        pipeline = Pipeline.from_pretrained(
            MODEL_NAME,
            use_auth_token=settings.hf_token,  # главный момент
        )
        pipeline.to(device)

        if not isinstance(pipeline, SpeakerDiarization):
            raise RuntimeError(f"Expected SpeakerDiarization, got {type(pipeline)}")

        log.info("Pipeline loaded successfully")
        return pipeline

    except Exception as exc:
        log.exception("Failed to load pyannote pipeline")
        raise RuntimeError(
            f"Не удалось загрузить {MODEL_NAME}. "
            f"Проверь токен HF и сеть. Ошибка: {exc}"
        ) from exc

# инициализация при импорте
_pipeline = _load_pipeline()

async def diarize(audio_path: str) -> list[dict]:
    """
    Возвращает список участников диалога формата:
    {"speaker":"spk_0", "start_ts":12.3, "end_ts":14.5}
    """
    log.debug(f"Starting diarization for {audio_path}")
    loop = get_running_loop()

    try:
        diarization = await loop.run_in_executor(
            None, lambda: _pipeline(audio_path)
        )
    except Exception as exc:
        log.exception(f"Diarization failed for {audio_path}")
        raise

    results = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        results.append(
            {
                "speaker": speaker,
                "start_ts": float(turn.start),
                "end_ts": float(turn.end),
            }
        )
    log.info(f"Diarization produced {len(results)} speaker turns for {audio_path}")
    return results
