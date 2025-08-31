from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # токен HuggingFace
    hf_token: str
    device: str = "cuda"
    # URL Ollama
    ollama_url: str
    # Название модели Ollama
    model_name_embeded: str
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