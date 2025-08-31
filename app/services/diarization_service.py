import torch
from pyannote.audio import Pipeline
from pyannote.audio.pipelines import SpeakerDiarization
from pathlib import Path
from app.config import settings
from app.logger import get_logger
import asyncio

log = get_logger(__name__)
MODEL_NAME = "pyannote/speaker-diarization"

def _load_pipeline() -> SpeakerDiarization:
    device = torch.device(settings.device if torch.cuda.is_available() else "cpu")
    pipeline = Pipeline.from_pretrained(MODEL_NAME, use_auth_token=settings.hf_token)
    pipeline.to(device)
    log.info("Pyannote pipeline loaded")
    return pipeline

_pipeline = _load_pipeline()

async def diarize_file(audio_path: str) -> list[dict]:
    """
    Разбивает аудио на сегменты по спикерам.
    Возвращает список:
    [{"speaker": "spk_0", "start_ts": 0.0, "end_ts": 10.5, "file_path": "/tmp/chunk_0.wav"}, ...]
    """
    loop = asyncio.get_running_loop()
    diarization = await loop.run_in_executor(None, lambda: _pipeline(audio_path))

    import torchaudio
    wav, sr = torchaudio.load(audio_path)
    base = Path(audio_path).stem
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
    return chunks
