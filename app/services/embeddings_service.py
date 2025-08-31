import httpx 
from typing import List

async def embed_text(text: str) -> List[float] | None:
    if not text:
        log.warning("Empty text passed to embed_text – returning None")
        return None

    url = f"{settings.ollama_url}/api/embeddings"
    payload = {"model": settings.model_name_embeded, "prompt": text}
    async with httpx.AsyncClient() as client:
        try:
            log.debug(f"Requesting embedding: model={settings.model_name_embeded}")
            resp = await client.post(url, json=payload, timeout=10.0)
            resp.raise_for_status()
            embedding = resp.json().get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("No 'embedding' list in response")
            log.debug(f"Received embedding of length {len(embedding)}")
            return embedding        # <‑‑ список чисел
        except httpx.HTTPError as exc:
            log.exception(f"HTTP error during embedding request to {url}: {exc}")
            return None