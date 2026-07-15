from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    app_name: str = "longcarebot"
    agent_url: str = "http://agent:8001"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "gemma4:e2b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
