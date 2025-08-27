import logging
from pathlib import Path
from .config import settings

# ────────────────────────────────────────
# 1️⃣ Форматтеры
# ────────────────────────────────────────
def _console_formatter() -> logging.Formatter:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    return logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S")


def _file_formatter() -> logging.Formatter:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    return logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S")


# ────────────────────────────────────────
# 2️⃣ Обработчики
# ────────────────────────────────────────
def _create_file_handler(path: str) -> logging.FileHandler:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(p, encoding="utf-8")
    handler.setLevel(logging.WARNING)   # prod: только предупреждения
    handler.setFormatter(_file_formatter())
    return handler


def _create_stream_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)      # dev: всё до DEBUG
    handler.setFormatter(_console_formatter())
    return handler


# ────────────────────────────────────────
# 3️⃣ Главная фабрика
# ────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """
    Возвращает готовый логгер. Если он уже создан – просто возвращаем его.
    """
    logger = logging.getLogger(name)

    # Не добавляем дублирующие обработчики
    if logger.handlers:
        return logger

    # Выбираем режим
    if settings.ollam_prod:
        logger.setLevel(logging.WARNING)
        logger.addHandler(_create_file_handler(settings.ollama_log_path))
    else:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_create_stream_handler())

    return logger


# ────────────────────────────────────────
__all__ = ["get_logger"]