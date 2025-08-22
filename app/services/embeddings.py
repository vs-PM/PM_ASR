import requests
import json
from app.config import settings

async def embed_text(text: str) -> str:
    """
    Возвращает строку JSON‑подобного массива
    (pgvector принимает строку, которую можно распарсить).
    """
    try:
        url = f"{settings.ollama_url}/api/embeddings"
        headers = {"Content-Type": "application/json"}
        data = {
            "model": settings.model_name_embeded,
            "prompt": text
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        embedding = response.json()["embedding"]

        return "{" + ",".join(str(v) for v in embedding) + "}"

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к Ollama: {e}")
        return None
