from app import main


def test_documents_endpoint_lists_pdfs(client):
    main.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (main.DATA_DIR / "alpha.pdf").write_bytes(b"%PDF-1.4\n")
    (main.DATA_DIR / "notes.txt").write_text("skip", encoding="utf-8")

    response = client.get("/documents")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["documents"] == ["alpha.pdf"]
