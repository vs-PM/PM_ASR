import torch
from pyannote.audio import Pipeline
from pyannote.audio.pipelines import SpeakerDiarization
from pyannote.audio.utils.reproducibility import ReproducibilityWarning
from pathlib import Path
from threading import Lock
import warnings, time
from app.config import settings
from app.logger import get_logger
import asyncio
import subprocess
import tempfile
import torchaudio

log = get_logger(__name__)
MODEL_NAME = "pyannote/speaker-diarization-3.1"

def _load_pipeline() -> SpeakerDiarization:
    device = torch.device(settings.device if torch.cuda.is_available() else "cpu")
    pipeline = Pipeline.from_pretrained(MODEL_NAME, use_auth_token=settings.hf_token)
    pipeline.to(device)
    log.info("Pyannote pipeline loaded")
    return pipeline

_pipeline: SpeakerDiarization | None = None
_pipeline_lock = Lock()
_pipeline = _load_pipeline()


def _load_pipeline_sync() -> SpeakerDiarization:
    token = settings.hf_token
    if not token:
        raise RuntimeError("HF token is empty. Set HF_TOKEN/HUGGINGFACEHUB_API_TOKEN or settings.hf_token")
    try:
        pipe = Pipeline.from_pretrained(MODEL_NAME, use_auth_token=token)
        if pipe is None:
            raise RuntimeError("Pipeline.from_pretrained returned None (likely gated; accept terms for all components).")
        device = torch.device(settings.device if torch.cuda.is_available() else "cpu")
        pipe.to(device)
        log.info("Pyannote pipeline loaded on %s", device)
        return pipe
    except Exception as e:
        log.exception("Failed to load %s", MODEL_NAME)
        raise

def get_pipeline() -> SpeakerDiarization:
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = _load_pipeline_sync()
    return _pipeline

warnings.filterwarnings("ignore", category=ReproducibilityWarning)
# раскомментировать для ускорения на NVIDIA:
# torch.backends.cuda.matmul.allow_tf32 = True
# torch.backends.cudnn.allow_tf32 = True

def _to_wav_16k_mono(src_path: str) -> str:
    """Конвертирует любой входной формат в временный WAV (mono, 16kHz). Возвращает путь к WAV."""
    dst_path = Path(tempfile.gettempdir()) / (Path(src_path).stem + "_16k_mono.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", src_path,
        "-ac", "1",             # mono
        "-ar", "16000",         # 16 kHz
        "-f", "wav",
        str(dst_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, text=True)
    except FileNotFoundError:
        log.exception("ffmpeg not found. Please install ffmpeg.")
        raise
    except subprocess.CalledProcessError as e:
        log.error("ffmpeg failed:\n%s", e.stderr)
        raise
    return str(dst_path)


async def diarize_file(audio_path: str) -> list[dict]:
    """
    Разбивает аудио на сегменты по спикерам.
    Возвращает список:
    [{"speaker": "spk_0", "start_ts": 0.0, "end_ts": 10.5, "file_path": "/tmp/chunk_0.wav"}, ...]
    """
    loop = asyncio.get_running_loop()
    # diarization = await loop.run_in_executor(None, lambda: _pipeline(audio_path))

    # 1) Гарантированно переводим в WAV 16k mono, чтобы обойти m4a и пр.
    wav_path = await loop.run_in_executor(None, lambda: _to_wav_16k_mono(audio_path))

    # 2) Получаем (или лениво создаём) пайплайн
    try:
        pipeline = await loop.run_in_executor(None, get_pipeline)
    except Exception as e:
        # Завалим задачу явной ошибкой (фон обработает)
        raise RuntimeError(f"pyannote pipeline init failed: {e}") from e

    diarization = await loop.run_in_executor(None, lambda: _pipeline(wav_path))
    # 3) Пропускаем через pyannote (важно: 3.x ждёт {"audio": path} / или waveform)
    t0 = time.time()
    try:
        diarization = await loop.run_in_executor(
            None, lambda: _pipeline({"audio": wav_path})
        )
        log.info(f"pyannote diarization done in {time.time() - t0:.2f}s for {wav_path}")
    except Exception as e:
        log.exception("pyannote pipeline failed")
        raise

    # 4) Грузим тот же WAV для нарезки чанков
    wav, sr = torchaudio.load(wav_path)
    base = Path(wav_path).stem
    tmp_dir = Path("/tmp/chunks")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    chunks = []
    for idx, (turn, _, speaker) in enumerate(diarization.itertracks(yield_label=True)):
        start_sample = int(turn.start * sr)
        end_sample = int(turn.end * sr)
        clip = wav[:, start_sample:end_sample]
        clip_path = tmp_dir / f"{base}_{speaker}_{idx}.wav"
        torchaudio.save(clip_path, clip, sr)
        chunks.append({
            "speaker": speaker,
            "start_ts": float(turn.start),
            "end_ts": float(turn.end),
            "file_path": str(clip_path)
        })
    log.info(f"Diarization produced {len(chunks)} chunks for {audio_path}")
    # 5) Чистим временный WAV
    try:
        Path(wav_path).unlink(missing_ok=True)
    except Exception:
        log.warning("Failed to remove temp wav: %s", wav_path)

    return chunks
