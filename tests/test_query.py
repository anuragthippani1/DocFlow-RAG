from app import main


class FakeQA:
    def __init__(self):
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return {
            "result": f"Answer for {payload['query']}",
            "source_documents": [FakeDoc({"file_name": "sample.pdf"})],
        }


class FakeDoc:
    def __init__(self, metadata):
        self.metadata = metadata


async def fake_agent(_answer):
    return {
        "risk_level": "Low",
        "reason": "Test agent reason.",
        "recommended_action": "Keep monitoring.",
    }


async def fake_external_agent(_answer, _external_context=None):
    return await fake_agent(_answer)


async def fake_decision(_agent_outputs):
    return {
        "final_risk": "Low",
        "final_decision": "Test final decision.",
        "priority_action": "No immediate action.",
    }


async def fake_external_context(_question):
    return {"enabled": False}


def patch_query_dependencies(monkeypatch, qa):
    monkeypatch.setattr(main, "vector_db_ready", lambda _path: True)
    monkeypatch.setattr(main, "get_qa", lambda: qa)
    monkeypatch.setattr(main, "fetch_external_risk_context", fake_external_context)
    monkeypatch.setattr(main, "analyze_supplier_async", fake_agent)
    monkeypatch.setattr(main, "analyze_inventory_async", fake_agent)
    monkeypatch.setattr(main, "analyze_logistics_async", fake_agent)
    monkeypatch.setattr(main, "analyze_external_risk_async", fake_external_agent)
    monkeypatch.setattr(main, "generate_final_decision_async", fake_decision)


def test_query_returns_503_when_vector_db_missing(client, monkeypatch):
    monkeypatch.setattr(main, "vector_db_ready", lambda _path: False)

    response = client.post("/query", json={"question": "What changed?"})

    assert response.status_code == 503
    assert response.json() == {"error": "No vector database found. Upload documents first."}


def test_query_endpoint_returns_agent_response(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)

    response = client.post("/query", json={"question": "What changed?"})

    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    payload = response.json()
    assert payload["answer"] == "Answer for What changed?"
    assert payload["sources"] == ["sample.pdf"]
    assert payload["decision"]["final_risk"] == "Low"
    assert payload.get("domain") in {"general", "research", "supply_chain"}
    assert "agents_run" in payload
    assert qa.calls == 1


def test_query_cache_returns_hit_on_repeated_question(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)

    first = client.post("/query", json={"question": "Repeat me"})
    second = client.post("/query", json={"question": "  repeat   me  "})
    stats = client.get("/stats")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert qa.calls == 1
    assert stats.json()["cache_hits"] == 1
