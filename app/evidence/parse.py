"""Small JSON object extractor for evidence LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, cast


def extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    except Exception:
        return None
    return None
