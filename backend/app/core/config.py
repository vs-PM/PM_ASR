# app/config.py
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # ───────── Hugging Face / Устройство ─────────
    hf_token: str = Field(..., description="Токен Hugging Face для pyannote (HF_TOKEN)")
    device: str = Field(..., description="Устройство инференса: 'cuda' или 'cpu' (DEVICE)")

    # ───────── Ollama ─────────
    ollama_url: str = Field(..., description="URL Ollama, напр. http://localhost:11434 (OLLAMA_URL)")
    embedding_model: str = Field(..., description="Модель эмбеддингов (EMBEDDING_MODEL)")
    summarize_model: str = Field(..., description="Модель суммаризации (SUMMARIZE_MODEL)")

    # Таймауты Ollama (секунды; 0 = без per-IO лимита)
    ollama_chat_timeout: int = Field(..., description="Общий guard-таймаут шага суммаризации (OLLAMA_CHAT_TIMEOUT)")
    ollama_connect_timeout: int = Field(..., description="Таймаут установления соединения (OLLAMA_CONNECT_TIMEOUT)")
    ollama_read_timeout: int = Field(..., description="Per-read таймаут; 0 = без лимита (OLLAMA_READ_TIMEOUT)")
    ollama_write_timeout: int = Field(..., description="Per-write таймаут; 0 = без лимита (OLLAMA_WRITE_TIMEOUT)")
    ollama_keep_alive: str = Field(..., description="Держать модель в памяти, напр. '30m' (OLLAMA_KEEP_ALIVE)")

    # ───────── Параметры суммаризации ─────────
    summarize_num_ctx: int = Field(..., description="Макс. длина контекста LLM (SUMMARIZE_NUM_CTX)")
    summarize_temperature: float = Field(..., description="Температура генерации (SUMMARIZE_TEMPERATURE)")
    summarize_top_p: float = Field(..., description="Top-p (SUMMARIZE_TOP_P)")
    summarize_num_predict_batch: int = Field(..., description="Токенов на каждом батч-шаге (SUMMARIZE_NUM_PREDICT_BATCH)")
    summarize_num_predict_final: int = Field(..., description="Токенов на финальном шаге (SUMMARIZE_NUM_PREDICT_FINAL)")

    # Ограничители текста (для аккуратной длины подсказок)
    max_refs_chars: int = Field(..., description="Лимит символов в блоке REF (MAX_REFS_CHARS)")
    max_draft_chars: int = Field(..., description="Лимит символов в черновике между шагами (MAX_DRAFT_CHARS)")
    max_final_draft_chars: int = Field(..., description="Лимит в финальном черновике (MAX_FINAL_DRAFT_CHARS)")

    # ───────── Параметры RAG ─────────
    rag_chunk_char_limit: int = Field(..., description="Лимит символов в батче до эмбеддинга (RAG_CHUNK_CHAR_LIMIT)")
    rag_top_k: int = Field(..., description="Сколько ближайших сегментов брать (RAG_TOP_K)")
    rag_min_score: float = Field(..., description="Минимальный скор сходства (RAG_MIN_SCORE)")

    # ───────── Сегментация ─────────
    vad_aggressiveness: int = Field(..., description="Агрессивность VAD 0..3 (VAD_AGGRESSIVENESS)")
    vad_frame_ms: int = Field(..., description="Фрейм VAD: 10/20/30 мс (VAD_FRAME_MS)")
    vad_min_speech_ms: int = Field(..., description="Мин. длит. речи, мс (VAD_MIN_SPEECH_MS)")
    vad_min_silence_ms: int = Field(..., description="Пауза для закрытия сегмента, мс (VAD_MIN_SILENCE_MS)")
    vad_merge_max_gap_sec: float = Field(..., description="Склейка пауз короче этого, сек (VAD_MERGE_MAX_GAP_SEC)")
    vad_max_segment_sec: float = Field(..., description="Макс. длина сегмента, сек (VAD_MAX_SEGMENT_SEC)")
    seg_overlap_sec: float = Field(..., description="Overlap при резке, сек (SEG_OVERLAP_SEC)")

    fixed_window_sec: float = Field(..., description="Длина окна в режиме fixed, сек (FIXED_WINDOW_SEC)")
    fixed_overlap_sec: float = Field(..., description="Overlap в режиме fixed, сек (FIXED_OVERLAP_SEC)")

    # ───────── FFmpeg ─────────
    ffmpeg_threads: int = Field(..., description="Потоки FFmpeg (0 = auto) (FFMPEG_THREADS)")
    ffmpeg_filter_threads: int = Field(..., description="Потоки фильтров (FFMPEG_FILTER_THREADS)")
    ffmpeg_probesize: str = Field(..., description="Размер пробы контейнера, напр. '1M' (FFMPEG_PROBESIZE)")
    ffmpeg_analyzeduration: str = Field(..., description="Длительность анализа, напр. '0' (FFMPEG_ANALYZEDURATION)")
    ffmpeg_use_soxr: bool = Field(..., description="Ресемплер soxr (FFMPEG_USE_SOXR)")

    # ───────── База данных ─────────
    ollama_db_host: str = Field(..., description="Хост PostgreSQL (OLLAMA_DB_HOST)")
    ollama_db_port: int = Field(..., description="Порт PostgreSQL (OLLAMA_DB_PORT)")
    ollama_db_name: str = Field(..., description="Имя БД (OLLAMA_DB_NAME)")
    ollama_db_user: str = Field(..., description="Пользователь БД (OLLAMA_DB_USER)")
    ollama_db_password: str = Field(..., description="Пароль БД (OLLAMA_DB_PASSWORD)")

    # ───────── Логирование ─────────
    ollam_prod: bool = Field(..., description="Прод-режим логирования (OLLAM_PROD)")
    ollama_log_path: str = Field(..., description="Файл логов (OLLAMA_LOG_PATH)")

    # ───────── Auth / JWT / Cookies ─────────
    jwt_secret: str = Field("change_me_dev_secret", description="Секрет для подписи JWT", alias="JWT_SECRET")
    jwt_algo: str = Field("HS256", description="Алгоритм подписи JWT", alias="JWT_ALGO")

    access_ttl_minutes: int = Field(15, description="TTL access-токена (мин.)", alias="ACCESS_TTL_MINUTES")
    refresh_ttl_days: int = Field(14, description="TTL refresh-токена (дн.)", alias="REFRESH_TTL_DAYS")

    cookie_domain: str | None = Field(None, description="Домен для auth-куки (опц.)", alias="COOKIE_DOMAIN")
    cookie_secure: bool = Field(True, description="Secure-флаг для auth-куки", alias="COOKIE_SECURE")
    
    upload_dir: str = "/data/uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    def get_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.ollama_db_user}:"
            f"{self.ollama_db_password}@{self.ollama_db_host}:"
            f"{self.ollama_db_port}/{self.ollama_db_name}"
        )

settings = Settings()
