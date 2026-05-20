import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openrouter-key")

from app import main


@pytest.fixture(autouse=True)
def isolated_app_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    main._clear_query_cache()
    main.get_qa.cache_clear()
    main._query_count = 0
    main._cache_hits = 0
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    yield
    main._clear_query_cache()
    cache_clear = getattr(main.get_qa, "cache_clear", None)
    if cache_clear:
        cache_clear()


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client
