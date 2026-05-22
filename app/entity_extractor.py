import json
from typing import Any

from app.agents._common import build_llm, extract_json_object
from app.logging_utils import get_logger

logger = get_logger(__name__)

ENTITY_TYPES = ("Person", "Organization", "Location", "Risk", "Document")


def extract_entities(text: str, file_name: str | None = None) -> dict[str, Any]:
    """Extract supply-chain entities and relationships from document text."""
    content = (text or "").strip()
    if not content:
        return {"entities": [], "relationships": []}

    prompt = (
        "Extract supply-chain entities and relationships from the document text.\n"
        "Return ONLY JSON with keys: entities, relationships.\n"
        "Entity object keys: name, type (Person|Organization|Location|Risk|Document).\n"
        "Relationship object keys: source, relation, target.\n"
        f"SOURCE_FILE: {file_name or 'unknown'}\n\n"
        f"TEXT:\n{content[:6000]}\n"
    )

    try:
        response = build_llm().invoke(prompt)
        payload = extract_json_object(str(response.content)) or {}
        entities = payload.get("entities") or []
        relationships = payload.get("relationships") or []
        if not isinstance(entities, list):
            entities = []
        if not isinstance(relationships, list):
            relationships = []
        return {"entities": entities, "relationships": relationships, "file_name": file_name}
    except Exception:
        logger.exception("Entity extraction failed for %s", file_name)
        return {"entities": [], "relationships": [], "file_name": file_name}
