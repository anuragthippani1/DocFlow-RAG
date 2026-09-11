"""Phase 3: deterministic structured conflict detection. No winner selection."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app import main
from app.evidence.answerability import ambiguous_verdict
from app.evidence.conflicts import apply_conflicts, conflict_explanation, detect_conflicts
from app.evidence.types import IntentResult
from tests.evidence_helpers import (
    documents_pack,
    patch_evidence_path,
    supported_outcome,
)
from tests.test_evidence_answerability import event_names, iter_sse_events
from tests.test_query import FakeQA, patch_query_dependencies

DELIVERY_QUESTION = "What is Supplier X's delivery lead time?"
INVENTORY_QUESTION = "How much inventory is available?"


def _delivery_conflict_pack():
    return documents_pack(
        DELIVERY_QUESTION,
        [
            ("supplier_a.pdf", "Supplier X delivery lead time is 12 days.", 3),
            ("supplier_b.pdf", "Supplier X delivery lead time is 19 days.", 6),
        ],
    )


def _inventory_conflict_pack():
    return documents_pack(
        INVENTORY_QUESTION,
        [
            ("warehouse_a.pdf", "Available inventory: 500 units."),
            ("warehouse_b.pdf", "Available inventory: 800 units."),
        ],
    )


def _non_conflict_pack():
    return documents_pack(
        DELIVERY_QUESTION,
        [
            ("supplier_a.pdf", "Supplier X delivery time is 12 days."),
            ("supplier_b.pdf", "Supplier X headquarters are in London."),
        ],
    )


def _side_values(conflicts) -> set[str]:
    return {side.value for conflict in conflicts for side in conflict.sides}


def _side_ids(conflicts) -> set[str]:
    return {side.evidence_id for conflict in conflicts for side in conflict.sides}


def test_a_duration_conflict_returns_both_sides():
    pack = _delivery_conflict_pack()
    labeled, _ = supported_outcome(pack)
    conflicts = detect_conflicts(DELIVERY_QUESTION, labeled)
    assert len(conflicts) >= 1
    conflict = conflicts[0]
    assert conflict.kind == "duration"
    assert conflict.slot == "supplier_delivery_time_days"
    assert _side_values(conflicts) == {"12 days", "19 days"}
    assert _side_ids(conflicts) == {"e1", "e2"}
    assert {side.document for side in conflict.sides} == {"supplier_a.pdf", "supplier_b.pdf"}
    assert all(side.span for side in conflict.sides)
    assert "authoritative" in conflict.summary.lower()
    assert "correct because" not in conflict.summary.lower()
    assert "newer" not in conflict.summary.lower()


def test_b_quantity_conflict_returns_both_sides():
    pack = _inventory_conflict_pack()
    labeled, _ = supported_outcome(pack)
    conflicts = detect_conflicts(INVENTORY_QUESTION, labeled)
    assert len(conflicts) >= 1
    assert conflicts[0].kind == "quantity"
    assert _side_values(conflicts) == {"500 units", "800 units"}
    assert _side_ids(conflicts) == {"e1", "e2"}


def test_c_unrelated_location_is_not_a_conflict():
    pack = _non_conflict_pack()
    labeled, _ = supported_outcome(pack)
    assert detect_conflicts(DELIVERY_QUESTION, labeled) == []
    _, verdict = apply_conflicts(DELIVERY_QUESTION, labeled, supported_outcome(pack)[1])
    assert verdict.verdict == "supported"
    assert verdict.conflicts == []


def test_d_conflict_overrides_supported_verdict():
    pack = _delivery_conflict_pack()
    labeled, supported = supported_outcome(pack)
    assert supported.verdict == "supported"
    updated_pack, verdict = apply_conflicts(DELIVERY_QUESTION, labeled, supported)
    assert verdict.verdict == "conflicting"
    assert verdict.unsupported_kind == "none"
    assert len(verdict.conflicts) >= 1
    assert set(verdict.evidence_ids) == {"e1", "e2"}
    assert {item.stance for item in updated_pack.items} == {"contradicts"}


def test_ambiguous_is_not_overridden_by_structured_values():
    pack = _delivery_conflict_pack()
    labeled, supported = supported_outcome(pack)
    intent = IntentResult(
        needs_clarification=True,
        clarification_question="Which supplier?",
        slots=["supplier"],
    )
    ambiguous = ambiguous_verdict(intent, DELIVERY_QUESTION)
    _, verdict = apply_conflicts(DELIVERY_QUESTION, labeled, ambiguous)
    assert verdict.verdict == "ambiguous"
    assert verdict.conflicts == []
    assert supported.verdict == "supported"


def test_irrelevant_price_values_are_not_invented_as_delivery_conflicts():
    pack = documents_pack(
        DELIVERY_QUESTION,
        [
            ("a.pdf", "Supplier X list price is $100."),
            ("b.pdf", "Supplier X list price is $125."),
        ],
    )
    labeled, _ = supported_outcome(pack)
    assert detect_conflicts(DELIVERY_QUESTION, labeled) == []


def test_g_explanation_mentions_both_sides_and_picks_no_winner():
    pack = _delivery_conflict_pack()
    labeled, supported = supported_outcome(pack)
    _, verdict = apply_conflicts(DELIVERY_QUESTION, labeled, supported)
    text = conflict_explanation(verdict)
    assert "12 days" in text
    assert "19 days" in text
    assert "supplier_a.pdf" in text
    assert "supplier_b.pdf" in text
    assert "does not resolve" in text.lower()
    assert "is correct" not in text.lower()
    assert "19 days is correct" not in text
    assert "12 days is correct" not in text


def test_e_conflicting_query_does_not_run_agents(client, monkeypatch):
    qa = FakeQA()
    patch_query_dependencies(monkeypatch, qa)
    generate_calls: list[str] = []
    pack = _delivery_conflict_pack()
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        answer="Supplier X's delivery time is 19 days.",
        generate_calls=generate_calls,
    )
    agent_mock = AsyncMock(side_effect=AssertionError("agents must not run"))
    monkeypatch.setattr(main, "_run_agents", agent_mock)

    response = client.post("/query", json={"question": DELIVERY_QUESTION})
    payload = response.json()
    assert payload["verdict"]["verdict"] == "conflicting"
    assert len(payload["verdict"]["conflicts"]) >= 1
    conflict = payload["verdict"]["conflicts"][0]
    assert conflict["kind"] == "duration"
    values = {side["value"] for side in conflict["sides"]}
    assert values == {"12 days", "19 days"}
    assert {side["evidence_id"] for side in conflict["sides"]} == {"e1", "e2"}
    assert "12 days" in payload["answer"]
    assert "19 days" in payload["answer"]
    assert "19 days is correct" not in payload["answer"]
    assert generate_calls == []
    assert qa.calls == 0
    assert payload["agents_run"] == []
    assert payload["decision"] is None
    assert "agents" in payload
    assert "domain" in payload
    assert "evidence" in payload
    assert "source_details" in payload
    agent_mock.assert_not_called()


def test_f_stream_emits_verdict_before_conflict_tokens(client, monkeypatch):
    stream_calls: list[str] = []
    generate_calls: list[str] = []
    patch_query_dependencies(monkeypatch, FakeQA())
    pack = _delivery_conflict_pack()
    patch_evidence_path(
        monkeypatch,
        main,
        pack=pack,
        verify_fn=lambda q, p: supported_outcome(p),
        answer="Supplier X's delivery time is 19 days.",
        generate_calls=generate_calls,
        stream_calls=stream_calls,
    )
    monkeypatch.setattr(main, "_run_agents", AsyncMock(side_effect=AssertionError("agents")))

    with client.stream(
        "POST",
        "/query/stream",
        json={"question": DELIVERY_QUESTION, "messages": []},
    ) as response:
        body = "".join(response.iter_text())
    events = iter_sse_events(body)
    names = event_names(events)
    assert names[0] == "sources"
    assert names[1] == "verdict"
    assert "token" in names
    assert names.index("verdict") < names.index("token")
    assert names[-1] == "done"
    verdict_event = events[1][1]
    assert verdict_event["verdict"] == "conflicting"
    sides = verdict_event["conflicts"][0]["sides"]
    assert {side["value"] for side in sides} == {"12 days", "19 days"}
    token_text = "".join(data.get("content", "") for name, data in events if name == "token")
    assert "12 days" in token_text
    assert "19 days" in token_text
    assert stream_calls == []
    assert generate_calls == []
    done = events[-1][1]
    assert done["agents_run"] == []
    assert done["decision"] is None
