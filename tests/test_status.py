from app.status import DocumentStatus, set_document_status, list_document_statuses


def test_document_status_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PATH", str(tmp_path / "data"))
    from app.config import get_settings

    get_settings.cache_clear()

    set_document_status("sample.pdf", DocumentStatus.QUEUED)
    set_document_status("sample.pdf", DocumentStatus.DONE)

    statuses = list_document_statuses()
    assert statuses["sample.pdf"]["status"] == DocumentStatus.DONE.value

    get_settings.cache_clear()
