import uvicorn
from fastapi import FastAPI
from app.router import router
from app.database import get_pool

app = FastAPI(
    title="Whisper ASR Service",
    description="Распознавание речи + диаризация + pgvector"
)

app.include_router(router)

@app.on_event("startup")
async def startup():
    # Инициализируем пул – создаём объект, но оставляем его открытым
    app.state.pool = await get_pool().__aenter__()

@app.on_event("shutdown")
async def shutdown():
    await get_pool().__aexit__(None, None, None)