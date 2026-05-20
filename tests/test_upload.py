from dataclasses import replace

from app import main


def test_upload_endpoint_saves_pdf_and_runs_ingestion(client, monkeypatch):
    called = {"ingested": False}

    def fake_ingest_documents():
        called["ingested"] = True

    monkeypatch.setattr(main, "ingest_documents", fake_ingest_documents)

    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "sample.pdf"
    assert called["ingested"] is True
    assert (main.DATA_DIR / "sample.pdf").exists()


def test_upload_rejects_non_pdf(client):
    response = client.post(
        "/upload",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF uploads are supported."


def test_upload_rejects_files_over_size_limit(client, monkeypatch):
    settings = replace(main.get_settings(), max_upload_size_mb=1)
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    response = client.post(
        "/upload",
        files={"file": ("large.pdf", b"x" * (1024 * 1024 + 1), "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded PDF exceeds 1 MB limit."
    assert not (main.DATA_DIR / "large.pdf").exists()
