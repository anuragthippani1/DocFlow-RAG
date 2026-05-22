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


def _list_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


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
    max_upload_size_mb: int
    cors_origins: list[str]
    weather_api_url: str | None
    news_api_url: str | None
    shipping_api_url: str | None
    api_key: str | None
    rate_limit_per_minute: int
    max_question_length: int
    hybrid_retrieval_enabled: bool
    rerank_enabled: bool
    bm25_fetch_k: int
    rerank_top_n: int
    langsmith_tracing: bool
    langsmith_api_key: str | None
    langsmith_project: str
    neo4j_uri: str | None
    neo4j_user: str | None
    neo4j_password: str | None
    graph_extraction_enabled: bool
    celery_enabled: bool
    redis_url: str


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
        max_upload_size_mb=_int_env("MAX_UPLOAD_SIZE_MB", 25),
        cors_origins=_list_env(
            "CORS_ORIGINS", ["http://127.0.0.1:5500", "http://localhost:5500"]
        ),
        weather_api_url=os.getenv("WEATHER_API_URL"),
        news_api_url=os.getenv("NEWS_API_URL"),
        shipping_api_url=os.getenv("SHIPPING_API_URL"),
        api_key=os.getenv("API_KEY") or None,
        rate_limit_per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 60),
        max_question_length=_int_env("MAX_QUESTION_LENGTH", 2000),
        hybrid_retrieval_enabled=_bool_env("HYBRID_RETRIEVAL_ENABLED", False),
        rerank_enabled=_bool_env("RERANK_ENABLED", False),
        bm25_fetch_k=_int_env("BM25_FETCH_K", 20),
        rerank_top_n=_int_env("RERANK_TOP_N", 8),
        langsmith_tracing=_bool_env("LANGCHAIN_TRACING_V2", False),
        langsmith_api_key=os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"),
        langsmith_project=os.getenv("LANGCHAIN_PROJECT", "docflow-rag"),
        neo4j_uri=os.getenv("NEO4J_URI"),
        neo4j_user=os.getenv("NEO4J_USER"),
        neo4j_password=os.getenv("NEO4J_PASSWORD"),
        graph_extraction_enabled=_bool_env("GRAPH_EXTRACTION_ENABLED", False),
        celery_enabled=_bool_env("CELERY_ENABLED", False),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
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
    if settings.max_upload_size_mb <= 0:
        missing.append("MAX_UPLOAD_SIZE_MB (> 0)")

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
