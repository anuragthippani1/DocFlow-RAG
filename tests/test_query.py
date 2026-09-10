import json

from langchain_core.documents import Document

from app import main
from app.evidence.pack import build_evidence_pack, source_details_from_pack


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


def test_followup_uses_conversation_history_not_stateless_qa(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    captured = {}

    def fake_retrieval(question, history):
        captured["question"] = question
        captured["history"] = history
        return (
            "most serious supply chain risk",
            [],
            [{"n": 1, "document": "sample.pdf", "excerpt": "Delay is the leading risk.", "page": 3}],
        )

    monkeypatch.setattr(main, "run_conversational_retrieval", fake_retrieval)
    monkeypatch.setattr(
        main, "generate_answer", lambda question, history, details: "Delay is the most serious risk [1]."
    )

    response = client.post(
        "/query",
        json={
            "question": "Which one is most serious?",
            "messages": [
                {"role": "user", "content": "What are the main supply chain risks?"},
                {"role": "assistant", "content": "Delay and cost overruns."},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert qa.calls == 0
    assert captured["question"] == "Which one is most serious?"
    assert captured["history"][0]["content"] == "What are the main supply chain risks?"
    assert captured["history"][1]["content"] == "Delay and cost overruns."
    assert payload["answer"] == "Delay is the most serious risk [1]."
    assert payload["source_details"][0]["document"] == "sample.pdf"
    assert payload["source_details"][0]["page"] == 3


def test_query_stream_emits_tokens_and_persists_conversation(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    captured = {}

    def fake_retrieval(question, history):
        captured["history"] = history
        return (
            question,
            [],
            [{"n": 1, "document": "sample.pdf", "excerpt": "Port congestion.", "page": 2}],
        )

    async def fake_stream(question, history, details):
        for token in ["Port ", "congestion ", "is the main risk [1]."]:
            yield token

    monkeypatch.setattr(main, "run_conversational_retrieval", fake_retrieval)
    monkeypatch.setattr(main, "astream_answer", fake_stream)

    conversation = client.post("/conversations", json={"title": "New conversation"}).json()
    with client.stream(
        "POST",
        "/query/stream",
        json={
            "question": "What are the main supply chain risks?",
            "conversation_id": conversation["id"],
            "messages": [],
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: sources" in body
    assert "event: token" in body
    assert "event: done" in body
    assert "Port congestion is the main risk [1]." in body
    assert qa.calls == 0

    detail = client.get(f"/conversations/{conversation['id']}").json()
    assert detail["title"] == "What are the main supply chain risks?"
    assert [item["role"] for item in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["sources"][0]["document"] == "sample.pdf"

    captured["history"] = None
    with client.stream(
        "POST",
        "/query/stream",
        json={
            "question": "Which one is most serious?",
            "conversation_id": conversation["id"],
            "messages": [],
        },
    ) as follow_up:
        follow_status = follow_up.status_code
        follow_body = "".join(follow_up.iter_text())

    assert follow_status == 200
    assert captured["history"]
    assert captured["history"][0]["content"] == "What are the main supply chain risks?"
    assert "event: done" in follow_body
    messages = client.get(f"/conversations/{conversation['id']}").json()["messages"]
    assert len(messages) == 4
    assert messages[2]["content"] == "Which one is most serious?"


def test_repeat_query_on_same_conversation_replaces_assistant(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    monkeypatch.setattr(
        main,
        "run_conversational_retrieval",
        lambda question, history: (question, [], [{"n": 1, "document": "sample.pdf", "excerpt": "x"}]),
    )
    monkeypatch.setattr(main, "generate_answer", lambda question, history, details: "Regenerated answer")

    conversation = client.post("/conversations", json={}).json()
    path = "/query"
    payload = {
        "question": "What changed?",
        "conversation_id": conversation["id"],
    }
    assert client.post(path, json=payload).status_code == 200
    assert client.post(path, json=payload).status_code == 200
    messages = client.get(f"/conversations/{conversation['id']}").json()["messages"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Regenerated answer"


def test_query_stream_sources_event_includes_evidence_pack(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    pack = build_evidence_pack(
        query="What are the main supply chain risks?",
        standalone_query="What are the main supply chain risks?",
        documents=[
            Document(
                page_content="Port congestion.",
                metadata={
                    "file_name": "sample.pdf",
                    "page_number": 1,
                    "_retrieval_backend": "hybrid",
                    "rerank_score": 0.7,
                },
            ),
            Document(
                page_content="Warehouse delay.",
                metadata={
                    "file_name": "other.pdf",
                    "page_number": 0,
                    "_retrieval_backend": "hybrid",
                    "rerank_score": 0.4,
                },
            ),
            Document(
                page_content="Customs hold.",
                metadata={
                    "file_name": "third.pdf",
                    "page_number": 2,
                    "_retrieval_backend": "hybrid",
                },
            ),
        ],
        retriever="hybrid_rerank",
    )
    details = source_details_from_pack(pack)

    def fake_retrieval(question, history):
        return question, [], details, pack

    async def fake_stream(question, history, passed_details):
        assert passed_details == details
        yield "Port congestion is the main risk [1]."

    monkeypatch.setattr(main, "run_conversational_retrieval", fake_retrieval)
    monkeypatch.setattr(main, "astream_answer", fake_stream)

    with client.stream(
        "POST",
        "/query/stream",
        json={"question": "What are the main supply chain risks?", "messages": []},
    ) as response:
        body = "".join(response.iter_text())

    assert "event: sources" in body
    assert "event: token" in body
    assert "event: verdict" not in body
    sources_event = None
    for block in body.split("\n\n"):
        if block.startswith("event: sources"):
            data_line = [line for line in block.split("\n") if line.startswith("data: ")][0]
            sources_event = json.loads(data_line[6:])
    assert sources_event is not None
    assert sources_event["sources"] == ["sample.pdf", "other.pdf"]
    assert sources_event["source_details"][0]["n"] == 1
    assert sources_event["source_details"][0]["document"] == "sample.pdf"
    assert "excerpt" in sources_event["source_details"][0]
    assert set(sources_event["source_details"][0]) <= {"n", "document", "page", "excerpt"}
    evidence = sources_event["evidence"]
    assert evidence["retriever"] == "hybrid_rerank"
    assert [item["id"] for item in evidence["items"]] == ["e1", "e2", "e3"]
    assert evidence["items"][0]["retrieval_rank"] == 1
    assert evidence["items"][0]["rerank_score"] == 0.7
    assert "rerank_score" not in evidence["items"][2]
    assert evidence["items"][0]["stance"] == "unknown"
    assert evidence["items"][0]["relevance"] == "uncertain"


def test_conversational_query_keeps_source_details_and_adds_evidence(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    pack = build_evidence_pack(
        query="Which one is most serious?",
        standalone_query="most serious supply chain risk",
        documents=[
            Document(
                page_content="Delay is the leading risk.",
                metadata={"file_name": "sample.pdf", "page_number": 2, "_retrieval_backend": "mmr"},
            )
        ],
        retriever="mmr",
    )
    details = [{"n": 1, "document": "sample.pdf", "excerpt": pack.items[0].excerpt, "page": 3}]

    monkeypatch.setattr(
        main,
        "run_conversational_retrieval",
        lambda question, history: ("most serious supply chain risk", [], details, pack),
    )
    monkeypatch.setattr(
        main, "generate_answer", lambda question, history, passed: "Delay is the most serious risk [1]."
    )

    response = client.post(
        "/query",
        json={
            "question": "Which one is most serious?",
            "messages": [
                {"role": "user", "content": "What are the main supply chain risks?"},
                {"role": "assistant", "content": "Delay and cost overruns."},
            ],
        },
    )
    payload = response.json()
    assert payload["sources"] == ["sample.pdf"]
    assert payload["source_details"][0]["document"] == "sample.pdf"
    assert payload["source_details"][0]["page"] == 3
    assert payload["evidence"]["retriever"] == "mmr"
    assert payload["evidence"]["items"][0]["id"] == "e1"
    assert payload["agents_run"] is not None
    assert "decision" in payload
    assert "domain" in payload

