import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_api_base: str
    openrouter_site_url: str
    openrouter_app_name: str
    embedding_model: str
    qa_model: str
    agent_model: str
    data_path: str
    db_path: str
    chunk_size: int
    chunk_overlap: int
    retriever_k: int
    retriever_fetch_k: int
    source_limit: int
    llm_timeout_seconds: float
    agent_timeout_seconds: float
    query_timeout_seconds: float
    external_risk_timeout_seconds: float
    query_cache_enabled: bool
    query_cache_max_size: int
    weather_api_url: str | None
    news_api_url: str | None
    shipping_api_url: str | None


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1"),
        openrouter_site_url=os.getenv("OPENROUTER_SITE_URL", ""),
        openrouter_app_name=os.getenv("OPENROUTER_APP_NAME", "DocFlow-RAG"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        qa_model=os.getenv("QA_MODEL", "gpt-3.5-turbo"),
        agent_model=os.getenv("AGENT_MODEL", "gpt-3.5-turbo"),
        data_path=os.getenv("DATA_PATH", "data/"),
        db_path=os.getenv("DB_PATH", "db/"),
        chunk_size=_int_env("CHUNK_SIZE", 500),
        chunk_overlap=_int_env("CHUNK_OVERLAP", 100),
        retriever_k=_int_env("RETRIEVER_K", 5),
        retriever_fetch_k=_int_env("RETRIEVER_FETCH_K", 20),
        source_limit=_int_env("SOURCE_LIMIT", 2),
        llm_timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", 45.0),
        agent_timeout_seconds=_float_env("AGENT_TIMEOUT_SECONDS", 60.0),
        query_timeout_seconds=_float_env("QUERY_TIMEOUT_SECONDS", 90.0),
        external_risk_timeout_seconds=_float_env("EXTERNAL_RISK_TIMEOUT_SECONDS", 4.0),
        query_cache_enabled=_bool_env("QUERY_CACHE_ENABLED", True),
        query_cache_max_size=_int_env("QUERY_CACHE_MAX_SIZE", 64),
        weather_api_url=os.getenv("WEATHER_API_URL"),
        news_api_url=os.getenv("NEWS_API_URL"),
        shipping_api_url=os.getenv("SHIPPING_API_URL"),
    )


def validate_settings(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    missing: list[str] = []

    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.openai_api_base:
        missing.append("OPENAI_API_BASE")
    if not settings.embedding_model:
        missing.append("EMBEDDING_MODEL")
    if not settings.qa_model:
        missing.append("QA_MODEL")
    if not settings.agent_model:
        missing.append("AGENT_MODEL")

    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            f"Missing required configuration: {joined}. "
            "Copy .env.example to .env and fill in the required values."
        )


def openrouter_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
