from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
     # ---- HF token ----
    hf_token: str

    # ---- Device ----
    device: str = "cuda"

    # ---- Ollama ----
    ollama_url: str
    embedding_model: str
    summarize_model: str 
    ollama_chat_timeout: int 
    ollama_connect_timeout: int 
    ollama_read_timeout: int 
    ollama_write_timeout: int 
    summarize_num_ctx: int              

    # ---- RAG params ----
    rag_chunk_char_limit: int              
    rag_top_k: int                           
    rag_min_score: float

    #----DB----
    ollama_db_host: str 
    ollama_db_port: int 
    ollama_db_name: str 
    ollama_db_user: str 
    ollama_db_password: str 

    # ----------  Логирование  ----------
    ollam_prod: bool 
    ollama_log_path: str

    def get_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.ollama_db_user}:"
            f"{self.ollama_db_password}@{self.ollama_db_host}:"
            f"{self.ollama_db_port}/{self.ollama_db_name}"
        )

    # привязка к .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",                # чтобы переменные читались без префикса
        case_sensitive=False,        # приёмный флаг
    )

# синглтон для всего проекта
settings = Settings()