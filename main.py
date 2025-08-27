import uvicorn
from fastapi import FastAPI
from app.router import router
from app.database import init_pool, get_pool, close_pool
from app.logger import get_logger


log = get_logger(__name__)

app = FastAPI(
    title="Whisper ASR Service",
    description="Распознавание речи + диаризация + pgvector",
)
app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    """
    При старте приложения создаём (или получаем) пул PostgreSQL‑соединений
    и сохраняем его в `app.state.pool` для дальнейшего использования
    в приложении (например, если кто‑то захочет получить его напрямую).
    """
    log.debug("Инициализируем пул соединений")
    await init_pool() 
    app.state.pool = await get_pool()
    log.debug(f"Пул сохранён в app.state.pool: {app.state.pool}")


@app.on_event("shutdown")
async def shutdown() -> None:
    """
    При завершении работы закрываем пул, чтобы все соединения корректно
    освобождались. Это особенно важно в продакшене (потенциальные leaks).
    """
    log.debug("Закрываем пул соединений")

    pool = getattr(app.state, "pool", None)
    if pool:
        await pool.close()
        log.info("Пул соединений закрыт")
    else:
        log.warning("Пул не был найден в state – возможно, он не создавался.")


if __name__ == "__main__":
    # `uvicorn.run()` автоматически инициализирует ASGI‑апп из строки модуля.
    # Путь `"app.main:app"` – это файл `main.py`, расположенный в пакете `app`.
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=7000,
        reload=False,          # в продакшене отключаем reload, но можно оставить True при dev‑рабочем режиме
    )