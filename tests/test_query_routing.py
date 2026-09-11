from app import main
from app.evidence.types import IntentResult
from tests.evidence_helpers import document_pack, patch_evidence_path, supported_outcome
from tests.test_query import FakeQA, patch_query_dependencies


async def fake_decision(_agent_outputs):
    return {
        "final_risk": "Low",
        "final_decision": "Monitor.",
        "priority_action": "No immediate action.",
    }


def test_query_routes_research_domain_with_mocked_rag(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    monkeypatch.setattr(main, "generate_final_decision_async", fake_decision)
    pack = document_pack(
        "What is GRAIL?",
        "This research paper discusses SLM-enhanced indexing.",
        document="GRAIL — SLM-Enhanced Indexing for Agent Discovery.pdf",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        answer="This research paper discusses SLM-enhanced indexing.",
    )
    monkeypatch.setattr(main, "analyze_intent", lambda q, h: IntentResult(
        needs_clarification=False, clarification_question=None, slots=[]
    ))

    response = client.post("/query", json={"question": "What is GRAIL?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] == "research"
    assert "supplier" not in payload["agents_run"]
    assert "skipped" in payload["agents"]["supplier"]["reason"].lower()
