import openai
import os

# Поставьте ваш ключ
openai.api_key = os.getenv("OPENAI_API_KEY")

async def embed_text(text: str) -> str:
    """
    Возвращает строку JSON‑подобного массива
    (pgvector принимает строку, которую можно распарсить).
    """
    resp = await openai.Embedding.acreate(
        model="text-embedding-ada-002",
        input=text
    )
    vec = resp["data"][0]["embedding"]  # список чисел
    # Преобразуем в строку, которую pgvector поймёт
    return "{" + ",".join(str(v) for v in vec) + "}"