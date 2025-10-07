import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import transcription, diarization, pipeline, embeddings, summary, protokol
from app.api.v1 import health, auth, admin
from app.api.v1 import ws as ws_api
from app.api.v1 import files as files_api
from app.api.v1 import transcripts as transcripts_api
from app.api.v1 import meetings as meetings_router
from app.api.v2 import segment as seg_v2
from app.api.v2 import transcripts as transcripts_v2
from app.db.session import async_engine
from app.core.logger import get_logger
from app.core.errors import install_exception_handlers
from app.core.config import settings

log = get_logger(__name__)
log.info(f"UPLOAD_DIR = {settings.upload_dir}")

app = FastAPI(
    title="Whisper ASR Service",
    description="Распознавание речи + диаризация + pgvector",
)


DEV_ORIGINS = [
    "https://pm.ingrivale.online",

]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,   # важно для куки
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Роутеры
# -------------------------------
app.include_router(transcription.router, prefix="/transcription")
app.include_router(diarization.router, prefix="/diarization")
app.include_router(pipeline.router, prefix="/pipeline")
app.include_router(embeddings.router, prefix="/embeddings")
app.include_router(summary.router, prefix="/summary")
app.include_router(protokol.router, prefix="/protokol")
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(ws_api.router, tags=["ws"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
app.include_router(transcripts_api.router, prefix="/api/v1/transcripts", tags=["transcripts"])
app.include_router(files_api.router, prefix="/api/v1/files", tags=["files"])
app.include_router(meetings_router.router, prefix="/api/v1/meetings", tags=["meetings"])
app.include_router(seg_v2.router, prefix="/api/v2/segment", tags=["v2-segmentation"])
app.include_router(transcripts_v2.router, prefix="/api/v2/transcripts", tags=["v2-transcripts"])


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
    await async_engine.dispose()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=7000, reload=False)
