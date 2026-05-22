import os

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


def configure_langsmith() -> None:
    """Enable LangSmith tracing when configured."""
    settings = get_settings()
    if not settings.langsmith_tracing:
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    logger.info("LangSmith tracing enabled for project %s", settings.langsmith_project)
