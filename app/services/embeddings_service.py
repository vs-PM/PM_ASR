import httpx 
from typing import List
from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)


async def embed_text(text: str) -> List[float] | None:
    if not text:
        log.warning("Empty text passed to embed_text – returning None")
        return None

    url = f"{settings.ollama_url}/api/embed"
    payload = {"model": settings.embedding_model, "input": text} 
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            log.debug(f"Requesting embedding: model={settings.embedding_model}")
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            # /api/embed возвращает "embeddings": [[...]] даже для одного input
            embeddings = data.get("embeddings")
            if not (isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list)):
                raise ValueError("No 'embeddings'[[...]] in response")
            vec = embeddings[0]
            log.debug(f"Received embedding of length {len(vec)}")
            return vec
        except httpx.HTTPError as exc:
            log.exception(f"HTTP error during embedding request to {url}: {exc}")
            return None