import torch
from faster_whisper import WhisperModel
from pathlib import Path
from app.logger import get_logger

log = get_logger(__name__)

MODEL_NAME = "small"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

log.info(f"Инициализация модели Whisper: {MODEL_NAME}, устройство: {DEVICE}")

try:
    # L4 поддерживает fp16 → быстрее и экономит память
    whisper = WhisperModel(MODEL_NAME, device=DEVICE, compute_type="float16")
    # прогрев контекста CUDA (важно для асинхронного окружения)
    if DEVICE == "cuda":
        _ = torch.randn(1).to("cuda")
    log.info("Модель Whisper успешно загружена")
except Exception:
    log.exception("Ошибка при загрузке модели Whisper")
    raise


async def transcribe_file(audio_path: str) -> str:
    """
    Транскрибирует аудиофайл и возвращает текст.
    Логирует каждый сегмент по мере получения.
    """
    log.info(f"Начало транскрипции файла: {audio_path}")
    if not Path(audio_path).exists():
        log.error(f"Аудиофайл не найден: {audio_path}")
        raise FileNotFoundError(f"Файл не найден: {audio_path}")

    transcribe_kwargs = dict(
        language="ru",
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    log.info(
        f"Вызов whisper.transcribe для файла {audio_path} "
        f"на устройстве {DEVICE}, язык={transcribe_kwargs['language']}"
    )

    try:
        # теперь без run_in_executor → прямой вызов
        segments, _info = whisper.transcribe(str(audio_path), **transcribe_kwargs)

        text = ""
        count = 0
        for seg in segments:
            count += 1
            text += seg.text
            log.info(
                # f"Сегмент {count}: start={seg.start:.2f}, end={seg.end:.2f}, "
                f"длина текста={len(seg.text)}, общий текст={len(text)}"
            )

        log.info(
            f"Транскрипция завершена для файла {audio_path}, "
            f"всего сегментов: {count}, общий текст длиной {len(text)} символов"
        )
        return text

    except Exception:
        log.exception(f"Ошибка при транскрипции файла {audio_path}")
        raise
