from app import main


def test_delete_document_removes_pdf(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "delete_document",
        lambda _name: {"message": "Deleted x.pdf", "filename": "x.pdf"},
    )

    response = client.delete("/documents/sample.pdf")
    assert response.status_code == 200
    assert response.json()["filename"] == "x.pdf"


def test_reindex_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "force_reindex",
        lambda: {"message": "Vector index rebuilt.", "documents": ["a.pdf"], "count": 1},
    )

    response = client.post("/documents/reindex")
    assert response.status_code == 200
    assert response.json()["count"] == 1
