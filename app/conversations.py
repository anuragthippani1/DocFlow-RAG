"""SQLite persistence for user-scoped conversations and messages."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from app.config import get_settings

API_KEY_HEADER = "X-API-Key"
WORKSPACE_HEADER = "X-Workspace-Id"
_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_MAX_HISTORY = 10


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_user_id(request: Request) -> str:
    key = (request.headers.get(API_KEY_HEADER) or "").strip()
    if key:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return f"key:{digest}"
    workspace = (request.headers.get(WORKSPACE_HEADER) or "").strip()
    if _WORKSPACE_RE.fullmatch(workspace):
        return f"ws:{workspace}"
    return "ws:anonymous"


def _db_path() -> Path:
    path = Path(get_settings().conversations_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversations_user
                ON conversations(user_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sources_json TEXT,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, created_at);
            """
        )


def title_from_question(question: str) -> str:
    cleaned = " ".join((question or "").split())
    if not cleaned:
        return "New conversation"
    if len(cleaned) <= 48:
        return cleaned
    cut = cleaned[:48].rsplit(" ", 1)[0]
    return f"{cut or cleaned[:48]}…"


def _row_conversation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "title": row["title"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _expand_sources_payload(sources: Any) -> dict[str, Any]:
    """Expose source_details as `sources` so existing clients keep working."""
    if not sources:
        return {}
    if isinstance(sources, dict) and (
        "source_details" in sources or "evidence" in sources or "verdict" in sources
    ):
        payload: dict[str, Any] = {
            "sources": sources.get("source_details") or [],
        }
        if sources.get("evidence") is not None:
            payload["evidence"] = sources["evidence"]
        if sources.get("verdict") is not None:
            payload["verdict"] = sources["verdict"]
        return payload
    if isinstance(sources, list):
        return {"sources": sources}
    return {}


def _row_message(row: sqlite3.Row) -> dict[str, Any]:
    sources = None
    raw = row["sources_json"]
    if raw:
        try:
            sources = json.loads(raw)
        except json.JSONDecodeError:
            sources = None
    payload = {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "createdAt": row["created_at"],
    }
    payload.update(_expand_sources_payload(sources))
    return payload


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_row_conversation(row) for row in rows]


def create_conversation(user_id: str, title: str | None = None) -> dict[str, Any]:
    init_db()
    now = utc_now()
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": (title or "New conversation").strip() or "New conversation",
        "created_at": now,
        "updated_at": now,
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, user_id, title, created_at, updated_at)
            VALUES (:id, :user_id, :title, :created_at, :updated_at)
            """,
            record,
        )
    return {
        "id": record["id"],
        "userId": user_id,
        "title": record["title"],
        "createdAt": now,
        "updatedAt": now,
    }


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return _row_conversation(row)


def rename_conversation(user_id: str, conversation_id: str, title: str) -> dict[str, Any]:
    cleaned = " ".join((title or "").split())
    if not cleaned:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip()
    get_conversation(user_id, conversation_id)
    now = utc_now()
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (cleaned, now, conversation_id, user_id),
        )
    return get_conversation(user_id, conversation_id)


def delete_conversation(user_id: str, conversation_id: str) -> None:
    get_conversation(user_id, conversation_id)
    with _connect() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )


def list_messages(user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    get_conversation(user_id, conversation_id)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
    return [_row_message(row) for row in rows]


def add_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | dict[str, Any] | None = None,
    *,
    set_title_if_default: bool = False,
) -> dict[str, Any]:
    conversation = get_conversation(user_id, conversation_id)
    now = utc_now()
    record_id = str(uuid.uuid4())
    sources_json = json.dumps(sources) if sources else None
    title = conversation["title"]
    if set_title_if_default and role == "user" and title in {"New conversation", "New chat"}:
        title = title_from_question(content)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, created_at, sources_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (record_id, conversation_id, role, content, now, sources_json),
        )
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conversation_id),
        )
    return {
        "id": record_id,
        "conversationId": conversation_id,
        "role": role,
        "content": content,
        "createdAt": now,
        **_expand_sources_payload(sources),
    }


def delete_message(user_id: str, conversation_id: str, message_id: str) -> None:
    get_conversation(user_id, conversation_id)
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM messages WHERE id = ? AND conversation_id = ?",
            (message_id, conversation_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Message not found.")
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )


def truncate_after(user_id: str, conversation_id: str, message_id: str, *, include: bool = False) -> None:
    messages = list_messages(user_id, conversation_id)
    index = next((i for i, item in enumerate(messages) if item["id"] == message_id), -1)
    if index < 0:
        raise HTTPException(status_code=404, detail="Message not found.")
    start = index if include else index + 1
    to_delete = [item["id"] for item in messages[start:]]
    if not to_delete:
        return
    with _connect() as conn:
        conn.executemany(
            "DELETE FROM messages WHERE id = ? AND conversation_id = ?",
            [(item_id, conversation_id) for item_id in to_delete],
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )


def update_message_content(user_id: str, conversation_id: str, message_id: str, content: str) -> dict[str, Any]:
    cleaned = (content or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    get_conversation(user_id, conversation_id)
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE messages
            SET content = ?, sources_json = NULL
            WHERE id = ? AND conversation_id = ? AND role = 'user'
            """,
            (cleaned, message_id, conversation_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="User message not found.")
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )
    messages = list_messages(user_id, conversation_id)
    return next(item for item in messages if item["id"] == message_id)


def history_for_llm(user_id: str, conversation_id: str) -> list[dict[str, str]]:
    messages = list_messages(user_id, conversation_id)
    trimmed = messages[-_MAX_HISTORY:]
    return [{"role": item["role"], "content": item["content"]} for item in trimmed]
