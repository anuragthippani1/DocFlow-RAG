import json
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


class DocumentStatus(StrEnum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    DONE = "Done"
    FAILED = "Failed"


def _status_file() -> Path:
    settings = get_settings()
    path = Path(settings.data_path) / ".ingestion_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_all() -> dict[str, Any]:
    path = _status_file()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Corrupt status file; resetting")
        return {}


def _save_all(data: dict[str, Any]) -> None:
    _status_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def set_document_status(filename: str, status: DocumentStatus, detail: str = "") -> dict[str, Any]:
    safe_name = Path(filename).name
    data = _load_all()
    data[safe_name] = {
        "status": status.value,
        "detail": detail,
        "updated_at": time.time(),
    }
    _save_all(data)
    return data[safe_name]


def get_document_status(filename: str) -> dict[str, Any] | None:
    return _load_all().get(Path(filename).name)


def list_document_statuses() -> dict[str, Any]:
    return _load_all()
