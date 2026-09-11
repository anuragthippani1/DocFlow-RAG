"""Deterministic v1 conflict detection for structured/numeric slots.

Detects incompatible values across evidence items. Does not pick a winner.
Semantic-only disagreement is out of scope for v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from typing import Hashable

from app.evidence.answerability import build_coverage, relabel_pack
from app.evidence.types import (
    Conflict,
    ConflictKind,
    ConflictSide,
    EvidenceItem,
    EvidencePack,
    EvidenceVerdict,
)

_DURATION = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_HYPHEN_DURATION = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)-(?P<unit>hour|day|week|month|year)\b",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*%")
_PRICE = re.compile(
    r"(?:(?P<sym>\$)|(?P<ccy>USD|EUR|GBP)\s*)(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"|(?P<num2>\d+(?:\.\d+)?)\s*(?P<ccy2>USD|EUR|GBP|dollars?)",
    re.IGNORECASE,
)
_QUANTITY = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>units?|items?|kg|kilograms?|tons?|tonnes?|pallets?|boxes|box|pieces|shipments?)\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
_US_DATE = re.compile(r"\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4})\b")
_NAMED_DATE = re.compile(
    r"\b(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(?P<d>\d{1,2}),\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
_MONTH_YEAR = re.compile(
    r"\b(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
_NAMED_ATTR = re.compile(
    r"\b(?P<attr>status|priority|tier|grade|region|model)\s*(?:is|:|=)\s*"
    r"(?P<val>[A-Za-z][A-Za-z0-9_-]*)\b",
    re.IGNORECASE,
)

_STATUS_PHRASES: tuple[tuple[str, str], ...] = (
    ("out of stock", "out_of_stock"),
    ("in stock", "in_stock"),
    ("on-time", "on_time"),
    ("on time", "on_time"),
)
_STATUS_WORDS = {
    "approved": "approved",
    "rejected": "rejected",
    "denied": "rejected",
    "open": "open",
    "closed": "closed",
    "active": "active",
    "inactive": "inactive",
    "suspended": "suspended",
    "delayed": "delayed",
    "available": "available",
    "unavailable": "unavailable",
    "enabled": "enabled",
    "disabled": "disabled",
}

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# Question/local hints → canonical slots. Longer, more specific hints first.
_SLOT_HINTS: tuple[tuple[str, tuple[str, ...], frozenset[str]], ...] = (
    (
        "supplier_delivery_time_days",
        (
            "delivery lead time",
            "lead time",
            "delivery time",
            "delivery",
            "transit time",
            "turnaround",
            "ship time",
        ),
        frozenset({"duration"}),
    ),
    ("warranty_duration", ("warranty",), frozenset({"duration"})),
    (
        "unit_price",
        ("unit price", "price", "cost", "fee", "charge"),
        frozenset({"price"}),
    ),
    (
        "inventory_quantity",
        (
            "available inventory",
            "inventory",
            "stock count",
            "quantity",
            "qty",
            "how many",
            "how much",
        ),
        frozenset({"quantity"}),
    ),
    (
        "percentage",
        ("percent", "percentage", "discount", "rate"),
        frozenset({"percentage"}),
    ),
    ("date", ("deadline", "due date", "as of", "date", "due"), frozenset({"date"})),
    ("status", ("status", "state"), frozenset({"status", "named_attribute"})),
    ("priority", ("priority",), frozenset({"named_attribute"})),
    ("tier", ("tier",), frozenset({"named_attribute"})),
    ("grade", ("grade",), frozenset({"named_attribute"})),
    ("region", ("region",), frozenset({"named_attribute"})),
    ("model", ("model",), frozenset({"named_attribute"})),
)

_SLOT_LABELS = {
    "supplier_delivery_time_days": "delivery-time",
    "warranty_duration": "warranty",
    "unit_price": "price",
    "inventory_quantity": "inventory",
    "percentage": "percentage",
    "date": "date",
    "status": "status",
}

_DURATION_HOURS = {
    "hour": 1.0,
    "hours": 1.0,
    "hr": 1.0,
    "hrs": 1.0,
    "day": 24.0,
    "days": 24.0,
    "week": 24.0 * 7,
    "weeks": 24.0 * 7,
    "month": 24.0 * 30,
    "months": 24.0 * 30,
    "year": 24.0 * 365,
    "years": 24.0 * 365,
}

_UNIT_SINGULAR = {
    "units": "unit",
    "items": "item",
    "kilograms": "kilogram",
    "tons": "ton",
    "tonnes": "tonne",
    "pallets": "pallet",
    "boxes": "box",
    "box": "box",
    "pieces": "piece",
    "shipments": "shipment",
}


@dataclass(frozen=True)
class _Fact:
    evidence_id: str
    document: str
    page: int | None
    span: str
    value: str
    kind: ConflictKind
    slot: str | None
    comparable: Hashable
    start: int
    end: int


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _singular_unit(raw: str) -> str:
    unit = raw.lower()
    if unit in _UNIT_SINGULAR:
        return _UNIT_SINGULAR[unit]
    if unit.endswith("s") and unit not in {"kg"}:
        return unit[:-1]
    return unit


def _overlaps(start: int, end: int, used: list[tuple[int, int]]) -> bool:
    return any(not (end <= u0 or start >= u1) for u0, u1 in used)


def _window(text: str, start: int, end: int, radius: int = 48) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _sentence_span(text: str, start: int, end: int) -> str:
    left = start
    while left > 0 and text[left - 1] not in ".\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in ".\n":
        right += 1
    return text[left:right].strip(" \t:,;") or text[start:end]


def _slot_from_text(kind: ConflictKind, text: str) -> str | None:
    blob = text.lower()
    for slot, hints, kinds in _SLOT_HINTS:
        if kind not in kinds:
            continue
        if any(hint in blob for hint in hints):
            return slot
    return None


def _question_targets(question: str) -> list[tuple[str, frozenset[str]]]:
    """Slots the question is actually asking about. Empty → do not invent conflicts."""
    seen: set[str] = set()
    targets: list[tuple[str, frozenset[str]]] = []
    blob = question.lower()
    for slot, hints, kinds in _SLOT_HINTS:
        if slot in seen:
            continue
        if any(hint in blob for hint in hints):
            seen.add(slot)
            targets.append((slot, kinds))
    return targets


def _eligible(item: EvidenceItem) -> bool:
    if item.relevance == "not_relevant":
        return False
    if item.stance == "unused":
        return False
    return True


def _item_text(item: EvidenceItem) -> str:
    return item.excerpt_full or item.excerpt or ""


def _append_fact(
    facts: list[_Fact],
    *,
    item: EvidenceItem,
    text: str,
    kind: ConflictKind,
    value: str,
    comparable: Hashable,
    start: int,
    end: int,
    used: list[tuple[int, int]],
    slot: str | None | object = ...,
) -> None:
    if _overlaps(start, end, used):
        return
    local = _window(text, start, end)
    resolved = _slot_from_text(kind, local) if slot is ... else slot
    facts.append(
        _Fact(
            evidence_id=item.id,
            document=item.document,
            page=item.page,
            span=_sentence_span(text, start, end),
            value=value,
            kind=kind,
            slot=resolved,
            comparable=comparable,
            start=start,
            end=end,
        )
    )
    used.append((start, end))


def _add_duration_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    for pattern in (_DURATION, _HYPHEN_DURATION):
        for match in pattern.finditer(text):
            unit = match.group("unit").lower()
            if unit.endswith("s") and unit not in _DURATION_HOURS:
                unit = unit[:-1]
            hours = _DURATION_HOURS.get(unit) or _DURATION_HOURS.get(unit + "s")
            if hours is None:
                continue
            amount = _parse_number(match.group("num"))
            _append_fact(
                facts,
                item=item,
                text=text,
                kind="duration",
                value=match.group(0).strip(),
                comparable=("duration", round(amount * hours, 6)),
                start=match.start(),
                end=match.end(),
                used=used,
            )


def _add_percent_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    for match in _PERCENT.finditer(text):
        amount = _parse_number(match.group("num"))
        _append_fact(
            facts,
            item=item,
            text=text,
            kind="percentage",
            value=match.group(0).strip(),
            comparable=("percentage", round(amount, 6)),
            start=match.start(),
            end=match.end(),
            used=used,
        )


def _add_price_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    for match in _PRICE.finditer(text):
        raw_num = match.group("num") or match.group("num2")
        if not raw_num:
            continue
        currency = (match.group("ccy") or match.group("ccy2") or match.group("sym") or "USD").upper()
        if currency == "$":
            currency = "USD"
        if currency.startswith("DOLLAR"):
            currency = "USD"
        amount = _parse_number(raw_num)
        _append_fact(
            facts,
            item=item,
            text=text,
            kind="price",
            value=match.group(0).strip(),
            comparable=("price", currency, round(amount, 6)),
            start=match.start(),
            end=match.end(),
            used=used,
        )


def _add_quantity_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    for match in _QUANTITY.finditer(text):
        amount = _parse_number(match.group("num"))
        unit = _singular_unit(match.group("unit"))
        _append_fact(
            facts,
            item=item,
            text=text,
            kind="quantity",
            value=match.group(0).strip(),
            comparable=("quantity", unit, round(amount, 6)),
            start=match.start(),
            end=match.end(),
            used=used,
        )


def _add_date_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    parsed: list[tuple[int, int, str, str]] = []
    for match in _ISO_DATE.finditer(text):
        try:
            value = date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        except ValueError:
            continue
        parsed.append((match.start(), match.end(), match.group(0), value.isoformat()))
    for match in _NAMED_DATE.finditer(text):
        month = _MONTHS.get(match.group("mon").lower())
        if not month:
            continue
        try:
            value = date(int(match.group("y")), month, int(match.group("d")))
        except ValueError:
            continue
        parsed.append((match.start(), match.end(), match.group(0), value.isoformat()))
    for match in _US_DATE.finditer(text):
        try:
            value = date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        except ValueError:
            continue
        parsed.append((match.start(), match.end(), match.group(0), value.isoformat()))
    for match in _MONTH_YEAR.finditer(text):
        month = _MONTHS.get(match.group("mon").lower())
        if not month:
            continue
        try:
            year = int(match.group("y"))
            date(year, month, 1)
        except ValueError:
            continue
        parsed.append((match.start(), match.end(), match.group(0), f"{year:04d}-{month:02d}"))
    for start, end, span, comparable in parsed:
        _append_fact(
            facts,
            item=item,
            text=text,
            kind="date",
            value=span.strip(),
            comparable=("date", comparable),
            start=start,
            end=end,
            used=used,
        )


def _add_status_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    lowered = text.lower()
    for phrase, canonical in _STATUS_PHRASES:
        start = 0
        while True:
            index = lowered.find(phrase, start)
            if index < 0:
                break
            end = index + len(phrase)
            start = end
            _append_fact(
                facts,
                item=item,
                text=text,
                kind="status",
                value=text[index:end],
                comparable=("status", canonical),
                start=index,
                end=end,
                used=used,
            )
    for match in re.finditer(r"\b([A-Za-z][A-Za-z-]+)\b", text):
        canonical = _STATUS_WORDS.get(match.group(1).lower())
        if not canonical:
            continue
        _append_fact(
            facts,
            item=item,
            text=text,
            kind="status",
            value=match.group(0),
            comparable=("status", canonical),
            start=match.start(),
            end=match.end(),
            used=used,
        )


def _add_named_attribute_facts(item: EvidenceItem, text: str, facts: list[_Fact], used: list[tuple[int, int]]) -> None:
    for match in _NAMED_ATTR.finditer(text):
        attr = match.group("attr").lower()
        value = match.group("val")
        _append_fact(
            facts,
            item=item,
            text=text,
            kind="named_attribute",
            value=value,
            comparable=("named_attribute", attr, value.lower()),
            start=match.start(),
            end=match.end(),
            used=used,
            slot=_slot_from_text("named_attribute", match.group(0)) or attr,
        )


def extract_facts(question: str, pack: EvidencePack) -> list[_Fact]:
    facts: list[_Fact] = []
    for item in pack.items:
        if not _eligible(item):
            continue
        text = _item_text(item)
        if not text:
            continue
        used: list[tuple[int, int]] = []
        _add_duration_facts(item, text, facts, used)
        _add_percent_facts(item, text, facts, used)
        _add_price_facts(item, text, facts, used)
        _add_quantity_facts(item, text, facts, used)
        _add_date_facts(item, text, facts, used)
        _add_status_facts(item, text, facts, used)
        _add_named_attribute_facts(item, text, facts, used)
    return facts


def _slot_label(slot: str) -> str:
    return _SLOT_LABELS.get(slot, slot.replace("_", " "))


def _summarize(slot: str, sides: list[ConflictSide]) -> str:
    label = _slot_label(slot)
    values = " and ".join(side.value for side in sides)
    return (
        f"The retrieved documents report different {label} values: {values}. "
        "The available evidence does not resolve which value should be treated as authoritative."
    )


def detect_conflicts(question: str, evidence_pack: EvidencePack) -> list[Conflict]:
    """Return structured conflicts relevant to the question. Never selects a winner."""
    targets = _question_targets(question)
    if not targets:
        return []

    grouped: dict[tuple[str, str], dict[Hashable, list[_Fact]]] = {}
    for fact in extract_facts(question, evidence_pack):
        for slot, kinds in targets:
            if fact.kind not in kinds:
                continue
            if fact.slot is not None and fact.slot != slot:
                continue
            remapped = replace(fact, slot=slot)
            grouped.setdefault((fact.kind, slot), {}).setdefault(remapped.comparable, []).append(remapped)
            break

    conflicts: list[Conflict] = []
    index = 1
    for (kind, slot), by_value in grouped.items():
        if len(by_value) < 2:
            continue
        sides: list[ConflictSide] = []
        seen_items: set[str] = set()
        for facts in by_value.values():
            representative = facts[0]
            if representative.evidence_id in seen_items:
                continue
            seen_items.add(representative.evidence_id)
            sides.append(
                ConflictSide(
                    evidence_id=representative.evidence_id,
                    document=representative.document,
                    page=representative.page,
                    span=representative.span,
                    value=representative.value,
                )
            )
        if len(sides) < 2:
            continue
        conflicts.append(
            Conflict(
                id=f"k{index}",
                slot=slot,
                kind=kind,  # type: ignore[arg-type]
                sides=sides,
                summary=_summarize(slot, sides),
            )
        )
        index += 1
    return conflicts


def conflict_explanation(verdict: EvidenceVerdict) -> str:
    """Deterministic explanation of both sides. Does not choose a value."""
    if not verdict.conflicts:
        return (
            "Your documents contain conflicting information. Both sides are shown; "
            "the available evidence does not resolve which value should be treated as authoritative."
        )
    blocks: list[str] = []
    for conflict in verdict.conflicts:
        label = _slot_label(conflict.slot)
        if len(conflict.sides) >= 2:
            first, second = conflict.sides[0], conflict.sides[1]
            lead = (
                f"Your documents contain conflicting {label} information: "
                f"{first.document} reports {first.value}, while {second.document} reports {second.value}."
            )
            extras = conflict.sides[2:]
            if extras:
                more = ", ".join(f"{side.document} reports {side.value}" for side in extras)
                lead = f"{lead} Additional values: {more}."
            blocks.append(lead)
        blocks.append(conflict.summary)
        for side in conflict.sides:
            page = f", page {side.page}" if side.page is not None else ""
            blocks.append(f"- {side.value} — {side.document}{page} [{side.evidence_id}]")
    return "\n".join(blocks)


def apply_conflicts(
    question: str,
    pack: EvidencePack,
    verdict: EvidenceVerdict,
) -> tuple[EvidencePack, EvidenceVerdict]:
    """Upgrade a verified turn to conflicting when structured values disagree."""
    if verdict.verdict == "ambiguous":
        return pack, verdict
    probe = pack.standalone_query or question
    conflicts = detect_conflicts(probe, pack)
    if not conflicts:
        return pack, verdict

    side_ids = {side.evidence_id for conflict in conflicts for side in conflict.sides}
    labels = {
        item.id: (
            item.relevance,
            "contradicts" if item.id in side_ids else item.stance,
        )
        for item in pack.items
    }
    labeled = relabel_pack(pack, labels)
    updated = verdict.model_copy(
        update={
            "verdict": "conflicting",
            "unsupported_kind": "none",
            "reason": conflicts[0].summary,
            "coverage": build_coverage(labeled),
            "evidence_ids": sorted(side_ids),
            "conflicts": conflicts,
            "missing_information": [],
        }
    )
    return labeled, updated
