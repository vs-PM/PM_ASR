import os
from pathlib import Path
from pyannote.audio import Pipeline
import torch
import torchaudio

MODEL_NAME = "pyannote/speaker-diarization"   # huggingface id
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

pipeline = Pipeline.from_pretrained(MODEL_NAME).to(DEVICE)

async def diarize(audio_path: str) -> list[dict]:
    """
    Возвращает список dict: {"speaker":"spk_0", "start":12.3, "end":14.5}
    """
    diarization = pipeline(audio_path)
    results = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        results.append({
            "speaker": speaker,
            "start_ts": turn.start,
            "end_ts": turn.end
        })
    return results