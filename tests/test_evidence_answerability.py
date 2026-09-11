"""Phase 2: evidence verification, answerability, and SSE token invariant."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from app import main
from app.evidence.answerability import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    apply_safety_rules,
    empty_pack,
)
from app.evidence.intent import analyze_intent, heuristic_intent
from app.evidence.types import IntentResult
from app.evidence.verify_openrouter import OpenRouterVerifier
from tests.evidence_helpers import (
    document_pack,
    patch_evidence_path,
    supported_outcome,
    unsupported_outcome,
)
from tests.test_query import patch_query_dependencies, FakeQA


def iter_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = None
        data = {}
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                data = json.loads(raw) if raw else {}
        if event_name:
            events.append((event_name, data))
    return events


def event_names(events: list[tuple[str, dict]]) -> list[str]:
    return [name for name, _ in events]


def test_heuristic_ambiguous_supplier_question():
    intent = heuristic_intent("What about the supplier?")
    assert intent is not None
    assert intent.needs_clarification is True
    assert intent.clarification_question
    assert "supplier" in intent.clarification_question.lower()


def test_analyze_intent_ambiguous_without_history():
    intent = analyze_intent("What about the supplier?", [])
    assert intent.needs_clarification is True
    assert intent.clarification_question


def test_safety_empty_pack_is_no_relevant_evidence():
    pack = empty_pack("What is the supplier revenue?")
    verdict = apply_safety_rules(
        pack, condition="supported_evidence", reason="should be ignored"
    )
    assert verdict.verdict == "unsupported"
    assert verdict.unsupported_kind == "no_relevant_evidence"


def test_safety_all_not_relevant_is_no_relevant_evidence():
    pack = document_pack("What is the supplier revenue?", "Office lunch menu and parking hours.")
    labeled, verdict = unsupported_outcome(
        pack, kind="no_relevant_evidence", reason="Unrelated office policy."
    )
    assert labeled.items[0].relevance == "not_relevant"
    assert verdict.verdict == "unsupported"
    assert verdict.unsupported_kind == "no_relevant_evidence"


def test_safety_never_upgrades_uncertainty_to_supported():
    pack = document_pack("Can the supplier meet our Q4 demand?", "The supplier is based in Austin.")
    verdict = apply_safety_rules(
        pack,
        condition="insufficient_evidence",
        reason="Mentions the supplier but not capacity.",
    )
    assert verdict.verdict == "unsupported"
    assert verdict.unsupported_kind == "insufficient_evidence"


def test_openrouter_verifier_maps_supported_json(monkeypatch):
    pack = document_pack(
        "What is the supplier delivery time?",
        "Supplier delivery time is 12 days.",
    )
    verifier = OpenRouterVerifier()
    monkeypatch.setattr(
        verifier,
        "_invoke",
        lambda question, evidence_pack: {
            "condition": "supported_evidence",
            "reason": "The excerpt states the delivery time.",
            "missing_information": [],
            "items": [{"id": "e1", "relevance": "relevant", "stance": "supports"}],
        },
    )
    labeled, verdict = verifier.verify_with_pack(
        "What is the supplier delivery time?", pack
    )
    assert labeled.items[0].stance == "supports"
    assert verdict.verdict == "supported"
    assert verdict.coverage.retrieved == 1
    assert "confidence" not in verdict.model_dump()


def test_supported_query_generates_after_verdict(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    generate_calls: list[str] = []
    pack = document_pack(
        "What is the supplier delivery time?",
        "Supplier delivery time is 12 days.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        answer="The supplier delivery time is 12 days [1].",
        generate_calls=generate_calls,
    )
    agent_mock = AsyncMock(wraps=main._run_agents)
    monkeypatch.setattr(main, "_run_agents", agent_mock)

    response = client.post("/query", json={"question": "What is the supplier delivery time?"})
    payload = response.json()
    assert payload["verdict"]["verdict"] == "supported"
    assert payload["answer"] == "The supplier delivery time is 12 days [1]."
    assert payload["source_details"][0]["n"] == 1
    assert payload["sources"]
    assert "agents" in payload
    assert "decision" in payload
    assert "domain" in payload
    assert "agents_run" in payload
    assert generate_calls == ["generate"]
    assert qa.calls == 0
    agent_mock.assert_awaited()


def test_unsupported_no_relevant_does_not_generate(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    generate_calls: list[str] = []
    pack = document_pack(
        "What is the supplier revenue?",
        "The cafeteria serves lunch from 12 to 2.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: unsupported_outcome(
            p, kind="no_relevant_evidence", reason="The excerpt is unrelated."
        ),
        generate_calls=generate_calls,
        stream_calls=generate_calls,
    )
    agent_mock = AsyncMock(side_effect=AssertionError("agents must not run"))
    monkeypatch.setattr(main, "_run_agents", agent_mock)

    response = client.post("/query", json={"question": "What is the supplier revenue?"})
    payload = response.json()
    assert payload["verdict"]["verdict"] == "unsupported"
    assert payload["verdict"]["unsupported_kind"] == "no_relevant_evidence"
    assert INSUFFICIENT_EVIDENCE_ANSWER in payload["answer"]
    assert generate_calls == []
    assert payload["agents_run"] == []
    assert payload["decision"] is None
    agent_mock.assert_not_called()
    assert qa.calls == 0


def test_unsupported_insufficient_does_not_generate(client, monkeypatch):
    generate_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack(
        "Can the supplier meet our Q4 demand?",
        "The supplier is a long-standing partner based in Austin.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: unsupported_outcome(
            p,
            kind="insufficient_evidence",
            reason="Mentions the supplier but not capacity or demand.",
        ),
        generate_calls=generate_calls,
    )
    monkeypatch.setattr(main, "_run_agents", AsyncMock(side_effect=AssertionError("agents")))

    payload = client.post(
        "/query", json={"question": "Can the supplier meet our Q4 demand?"}
    ).json()
    assert payload["verdict"]["verdict"] == "unsupported"
    assert payload["verdict"]["unsupported_kind"] == "insufficient_evidence"
    assert generate_calls == []
    assert payload["decision"] is None


def test_ambiguous_query_returns_clarification(client, monkeypatch):
    generate_calls: list[str] = []
    stream_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack("What about the supplier?", "Supplier delivery time is 12 days.")
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        generate_calls=generate_calls,
        stream_calls=stream_calls,
    )
    monkeypatch.setattr(
        main,
        "analyze_intent",
        lambda q, h: IntentResult(
            needs_clarification=True,
            clarification_question="Which supplier would you like me to analyze?",
            slots=["supplier"],
        ),
    )
    monkeypatch.setattr(main, "_run_agents", AsyncMock(side_effect=AssertionError("agents")))

    payload = client.post("/query", json={"question": "What about the supplier?"}).json()
    assert payload["verdict"]["verdict"] == "ambiguous"
    assert payload["verdict"]["clarification_question"]
    assert payload["answer"] == "Which supplier would you like me to analyze?"
    assert generate_calls == []
    assert payload["agents_run"] == []
    assert payload["decision"] is None


def test_stream_supported_emits_verdict_before_tokens(client, monkeypatch):
    stream_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack(
        "What is the supplier delivery time?",
        "Supplier delivery time is 12 days.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        answer="The supplier delivery time is 12 days [1].",
        stream_calls=stream_calls,
    )

    with client.stream(
        "POST",
        "/query/stream",
        json={"question": "What is the supplier delivery time?", "messages": []},
    ) as response:
        body = "".join(response.iter_text())
    events = iter_sse_events(body)
    names = event_names(events)
    assert names[0] == "sources"
    assert names[1] == "verdict"
    assert "token" in names
    assert names.index("verdict") < names.index("token")
    assert names[-1] == "done"
    assert events[1][1]["verdict"] == "supported"
    assert stream_calls == ["stream"]


def test_stream_unsupported_emits_no_tokens(client, monkeypatch):
    stream_calls: list[str] = []
    generate_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack(
        "What is the supplier revenue?",
        "The cafeteria serves lunch from 12 to 2.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: unsupported_outcome(
            p, kind="no_relevant_evidence", reason="Unrelated."
        ),
        generate_calls=generate_calls,
        stream_calls=stream_calls,
    )
    monkeypatch.setattr(main, "_run_agents", AsyncMock(side_effect=AssertionError("agents")))

    with client.stream(
        "POST",
        "/query/stream",
        json={"question": "What is the supplier revenue?", "messages": []},
    ) as response:
        body = "".join(response.iter_text())
    names = event_names(iter_sse_events(body))
    assert "token" not in names
    assert names == ["sources", "verdict", "done"]
    assert stream_calls == []
    assert generate_calls == []
    assert INSUFFICIENT_EVIDENCE_ANSWER in body


def test_stream_ambiguous_emits_no_tokens(client, monkeypatch):
    stream_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack("What about the supplier?", "unused")
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        stream_calls=stream_calls,
    )
    monkeypatch.setattr(
        main,
        "analyze_intent",
        lambda q, h: IntentResult(
            needs_clarification=True,
            clarification_question="Which supplier would you like me to analyze?",
            slots=["supplier"],
        ),
    )
    monkeypatch.setattr(main, "_run_agents", AsyncMock(side_effect=AssertionError("agents")))

    with client.stream(
        "POST",
        "/query/stream",
        json={"question": "What about the supplier?", "messages": []},
    ) as response:
        body = "".join(response.iter_text())
    names = event_names(iter_sse_events(body))
    assert "token" not in names
    assert "sources" not in names
    assert names == ["verdict", "done"]
    assert stream_calls == []


def test_verifier_failure_fails_closed(client, monkeypatch):
    generate_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack(
        "What is the supplier delivery time?",
        "Supplier delivery time is 12 days.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: (_ for _ in ()).throw(RuntimeError("verifier down")),
        generate_calls=generate_calls,
    )
    monkeypatch.setattr(main, "_run_agents", AsyncMock(side_effect=AssertionError("agents")))

    payload = client.post(
        "/query", json={"question": "What is the supplier delivery time?"}
    ).json()
    assert payload["verdict"]["verdict"] == "unsupported"
    assert payload["verdict"]["unsupported_kind"] == "insufficient_evidence"
    assert "verification_failed" in payload["verdict"]["missing_information"]
    assert generate_calls == []


def test_pipeline_verify_evidence_fail_closed(monkeypatch):
    pack = document_pack("q", "text")

    class Boom:
        def verify(self, question, evidence_pack):
            raise RuntimeError("down")

        def verify_with_pack(self, question, evidence_pack):
            raise RuntimeError("down")

    monkeypatch.setattr("app.evidence.pipeline.get_verifier", lambda: Boom())
    from app.evidence.pipeline import verify_evidence

    labeled, verdict = verify_evidence("q", pack)
    assert verdict.verdict == "unsupported"
    assert verdict.unsupported_kind == "insufficient_evidence"
    assert labeled is pack


def test_evidence_and_verdict_are_persisted(client, monkeypatch):
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = document_pack(
        "What is the supplier delivery time?",
        "Supplier delivery time is 12 days.",
    )
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        answer="The supplier delivery time is 12 days [1].",
    )
    conversation = client.post("/conversations", json={}).json()
    client.post(
        "/query",
        json={
            "question": "What is the supplier delivery time?",
            "conversation_id": conversation["id"],
        },
    )
    messages = client.get(f"/conversations/{conversation['id']}").json()["messages"]
    assistant = messages[1]
    assert assistant["sources"][0]["document"]
    assert assistant["verdict"]["verdict"] == "supported"
    assert assistant["evidence"]["items"][0]["id"] == "e1"
