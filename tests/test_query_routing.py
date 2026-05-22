from app import main
from tests.test_query import FakeDoc, patch_query_dependencies


async def fake_decision(_agent_outputs):
    return {
        "final_risk": "Low",
        "final_decision": "Monitor.",
        "priority_action": "No immediate action.",
    }


class ResearchQA:
    def invoke(self, _payload):
        return {
            "result": "This research paper discusses SLM-enhanced indexing.",
            "source_documents": [
                FakeDoc({"file_name": "GRAIL — SLM-Enhanced Indexing for Agent Discovery.pdf"})
            ],
        }


def test_query_routes_research_domain_with_mocked_rag(client, monkeypatch):
    patch_query_dependencies(monkeypatch, ResearchQA())
    monkeypatch.setattr(main, "generate_final_decision_async", fake_decision)

    response = client.post("/query", json={"question": "What is GRAIL?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] == "research"
    assert "supplier" not in payload["agents_run"]
    assert "skipped" in payload["agents"]["supplier"]["reason"].lower()
