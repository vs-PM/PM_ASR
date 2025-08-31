import uvicorn
from fastapi import FastAPI
from app.v2.routers import transcription, diarization, pipeline, embeddings
from app.database import engine
from app.logger import get_logger

log = get_logger(__name__)

app = FastAPI(
    title="Whisper ASR Service",
    description="Распознавание речи + диаризация + pgvector",
)

# -------------------------------
# Роутеры
# -------------------------------
app.include_router(transcription.router, prefix="/transcription")
app.include_router(diarization.router, prefix="/diarization")
app.include_router(pipeline.router, prefix="/pipeline")
app.include_router(embeddings.router, prefix="/embeddings")

# -------------------------------
# События старта и остановки
# -------------------------------
@app.on_event("startup")
async def startup():
    log.info("Application startup")
    # Если Alembic используется, таблицы создаются через миграции

@app.on_event("shutdown")
async def shutdown():
    log.info("Application shutdown")
    await engine.dispose()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=7000, reload=False)
