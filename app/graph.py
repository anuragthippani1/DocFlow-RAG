from typing import Any

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


class KnowledgeGraphStore:
    """Optional Neo4j-backed knowledge graph. No-ops when Neo4j is not configured."""

    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(
            settings.graph_extraction_enabled
            and settings.neo4j_uri
            and settings.neo4j_user
            and settings.neo4j_password
        )
        self._driver = None
        if self._enabled:
            try:
                from neo4j import GraphDatabase

                self._driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                )
            except Exception:
                logger.exception("Failed to connect to Neo4j; graph storage disabled")
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._driver is not None

    def upsert_extraction(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return

        file_name = payload.get("file_name") or "unknown"
        entities = payload.get("entities") or []
        relationships = payload.get("relationships") or []

        assert self._driver is not None
        with self._driver.session() as session:
            session.run(
                "MERGE (d:Document {name: $name}) SET d.updated_at = timestamp()",
                name=file_name,
            )
            for entity in entities:
                name = str(entity.get("name", "")).strip()
                entity_type = str(entity.get("type", "Risk")).strip() or "Risk"
                if not name:
                    continue
                session.run(
                    f"MERGE (e:{entity_type} {{name: $name}}) "
                    "MERGE (d:Document {name: $file}) MERGE (d)-[:MENTIONS]->(e)",
                    name=name,
                    file=file_name,
                )
            for rel in relationships:
                source = str(rel.get("source", "")).strip()
                target = str(rel.get("target", "")).strip()
                relation = str(rel.get("relation", "RELATED_TO")).strip() or "RELATED_TO"
                if not source or not target:
                    continue
                session.run(
                    f"MATCH (a {{name: $source}}), (b {{name: $target}}) "
                    f"MERGE (a)-[:{relation}]->(b)",
                    source=source,
                    target=target,
                )

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()


_graph_store: KnowledgeGraphStore | None = None


def get_graph_store() -> KnowledgeGraphStore:
    global _graph_store
    if _graph_store is None:
        _graph_store = KnowledgeGraphStore()
    return _graph_store
