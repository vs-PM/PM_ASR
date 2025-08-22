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

    def get_dsn(self) -> str:
        return f"postgresql://{self.ollama_db_user}:{self.ollama_db_password}@{self.ollama_db_host}:{self.ollama_db_port}/{self.ollama_db_name}"


    # привязка к .env
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# синглтон для всего проекта
settings = Settings()