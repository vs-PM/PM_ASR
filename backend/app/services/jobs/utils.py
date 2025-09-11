from pathlib import Path
import torch
from app.core.logger import get_logger

log = get_logger(__name__)

def clear_cuda_cache() -> None:
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        log.debug("CUDA cache cleared")

def safe_unlink(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        log.warning("Cannot remove temp file: %s", path)
