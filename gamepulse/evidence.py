"""SQLite Evidence Store with explicit public/private query boundaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from pydantic import Field

from .models import (
    CollectionRun,
    ContractModel,
    EvidenceItem,
    FactRecord,
    PrivateDataset,
    QueryPlan,
)


EVIDENCE_STORE_SCHEMA_VERSION = 1
COMMUNITY_KINDS = {"review", "post", "comment", "video", "survey_response", "support_record"}


class UpsertSummary(ContractModel):
    received: int = Field(ge=0)
    inserted: int = Field(ge=0)
    updated: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    likely_cross_posts: int = Field(ge=0)


def content_fingerprint(text: str) -> str:
    normalised = unicodedata.normalize("NFKC", text).casefold()
    normalised = " ".join(normalised.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _identity_key(item: EvidenceItem) -> str:
    dataset = item.dataset_id or "public"
    value = f"{item.access_scope.value}|{dataset}|{item.source}|{item.source_content_id}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EvidenceStore:
    """One-process MVP store; no server or vector index is involved."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS private_datasets (
                    dataset_id TEXT PRIMARY KEY,
                    owner_scope TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    identity_key TEXT NOT NULL UNIQUE,
                    access_scope TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    owner_scope TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_content_id TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL,
                    relevance_label TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    query_id TEXT,
                    content_fingerprint TEXT NOT NULL,
                    source_url TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_scope_game
                    ON evidence(access_scope, dataset_id, owner_scope, game_id, relevance_label);
                CREATE INDEX IF NOT EXISTS idx_evidence_fingerprint
                    ON evidence(content_fingerprint);
                CREATE TABLE IF NOT EXISTS evidence_query_links (
                    evidence_id TEXT NOT NULL,
                    query_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    language TEXT,
                    intent TEXT,
                    query_text TEXT,
                    alias_ids_json TEXT NOT NULL,
                    PRIMARY KEY (evidence_id, query_id),
                    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL,
                    source_evidence_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_facts_game ON facts(game_id);
                """
            )
            existing = connection.execute(
                "SELECT value FROM store_meta WHERE key = 'schema_version'"
            ).fetchone()
            if existing and int(existing["value"]) != EVIDENCE_STORE_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported Evidence Store schema {existing['value']}; "
                    f"expected {EVIDENCE_STORE_SCHEMA_VERSION}"
                )
            connection.execute(
                "INSERT OR REPLACE INTO store_meta(key, value) VALUES ('schema_version', ?)",
                (str(EVIDENCE_STORE_SCHEMA_VERSION),),
            )

    @property
    def schema_version(self) -> int:
        return EVIDENCE_STORE_SCHEMA_VERSION

    def register_private_dataset(self, dataset: PrivateDataset) -> None:
        if not dataset.authorisation_attested:
            raise ValueError("private dataset registration requires authorisation attestation")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO private_datasets(dataset_id, owner_scope, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    owner_scope = excluded.owner_scope,
                    payload_json = excluded.payload_json
                """,
                (dataset.dataset_id, dataset.owner_scope, json.dumps(dataset.to_dict(), ensure_ascii=False)),
            )

    def _validate_private_scope(
        self,
        connection: sqlite3.Connection,
        *,
        dataset_id: str,
        owner_scope: str,
    ) -> None:
        row = connection.execute(
            "SELECT owner_scope FROM private_datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        if row is None:
            raise PermissionError("private dataset is not registered")
        if row["owner_scope"] != owner_scope:
            raise PermissionError("private dataset owner scope does not match")

    def upsert_evidence(
        self,
        items: Iterable[EvidenceItem],
        *,
        query_plans: Iterable[QueryPlan] = (),
        owner_scope: str | None = None,
    ) -> UpsertSummary:
        items = list(items)
        plans = {plan.query_id: plan for plan in query_plans}
        inserted = 0
        updated = 0
        cross_posts = 0
        with self._connection() as connection:
            for item in items:
                dataset_key = item.dataset_id or ""
                owner_key = owner_scope or ""
                if item.retrieval_method.value == "user_upload" and item.access_scope.value != "private":
                    raise PermissionError("user uploads default to private and require a dataset scope")
                if item.access_scope.value == "private":
                    if not item.dataset_id or not owner_scope:
                        raise PermissionError("private evidence requires dataset_id and owner_scope")
                    self._validate_private_scope(
                        connection,
                        dataset_id=item.dataset_id,
                        owner_scope=owner_scope,
                    )
                elif item.dataset_id is not None or owner_scope is not None:
                    raise ValueError("public evidence cannot be assigned a private dataset/owner scope")

                identity = _identity_key(item)
                fingerprint = content_fingerprint(item.original_text)
                existing = connection.execute(
                    "SELECT evidence_id FROM evidence WHERE identity_key = ?",
                    (identity,),
                ).fetchone()
                evidence_id = existing["evidence_id"] if existing else item.evidence_id
                if existing:
                    updated += 1
                else:
                    inserted += 1
                cross_post = connection.execute(
                    """
                    SELECT 1 FROM evidence
                    WHERE content_fingerprint = ? AND identity_key != ?
                    LIMIT 1
                    """,
                    (fingerprint, identity),
                ).fetchone()
                if cross_post:
                    cross_posts += 1
                stored_item = item if evidence_id == item.evidence_id else item.model_copy(update={"evidence_id": evidence_id})
                connection.execute(
                    """
                    INSERT INTO evidence(
                        evidence_id, identity_key, access_scope, dataset_id, owner_scope,
                        game_id, source, source_content_id, evidence_kind, relevance_label,
                        run_id, query_id, content_fingerprint, source_url, payload_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(identity_key) DO UPDATE SET
                        relevance_label = excluded.relevance_label,
                        run_id = excluded.run_id,
                        query_id = excluded.query_id,
                        content_fingerprint = excluded.content_fingerprint,
                        source_url = excluded.source_url,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        evidence_id,
                        identity,
                        item.access_scope.value,
                        dataset_key,
                        owner_key,
                        item.game_id,
                        item.source,
                        item.source_content_id,
                        item.evidence_kind.value,
                        item.relevance_label.value,
                        item.run_id,
                        item.query_id,
                        fingerprint,
                        item.source_url,
                        json.dumps(stored_item.to_dict(), ensure_ascii=False, sort_keys=True),
                        item.retrieved_at.isoformat(),
                    ),
                )
                if item.query_id:
                    self._upsert_query_link(connection, evidence_id, item, plans.get(item.query_id))
        return UpsertSummary(
            received=len(items),
            inserted=inserted,
            updated=updated,
            duplicates=updated,
            likely_cross_posts=cross_posts,
        )

    @staticmethod
    def _upsert_query_link(
        connection: sqlite3.Connection,
        evidence_id: str,
        item: EvidenceItem,
        plan: QueryPlan | None,
    ) -> None:
        provenance = item.source_metadata.get("query_provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        connection.execute(
            """
            INSERT OR REPLACE INTO evidence_query_links(
                evidence_id, query_id, run_id, source, language, intent, query_text, alias_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                item.query_id,
                item.run_id,
                plan.source if plan else str(provenance.get("source") or item.source),
                plan.language if plan else provenance.get("language"),
                plan.intent.value if plan else provenance.get("query_intent"),
                plan.query_text if plan else provenance.get("actual_query"),
                json.dumps(
                    list(plan.alias_ids) if plan else list(item.matched_alias_ids),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )

    def save_run(self, run: CollectionRun) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO runs(run_id, payload_json) VALUES (?, ?)",
                (run.run_id, json.dumps(run.to_dict(), ensure_ascii=False, sort_keys=True)),
            )

    def get_run(self, run_id: str) -> CollectionRun | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return CollectionRun.model_validate_json(row["payload_json"]) if row else None

    def upsert_facts(self, facts: Iterable[FactRecord]) -> int:
        facts = list(facts)
        with self._connection() as connection:
            for fact in facts:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO facts(fact_id, game_id, source_evidence_id, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        fact.fact_id,
                        fact.game_id,
                        fact.source_evidence_id,
                        json.dumps(fact.to_dict(), ensure_ascii=False, sort_keys=True),
                    ),
                )
        return len(facts)

    def query_facts(self, game_id: str) -> list[FactRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM facts WHERE game_id = ? ORDER BY fact_id",
                (game_id,),
            ).fetchall()
        return [FactRecord.model_validate_json(row["payload_json"]) for row in rows]

    def query_public(
        self,
        *,
        game_id: str | None = None,
        relevance_label: str | None = None,
        community_only: bool = False,
    ) -> list[EvidenceItem]:
        clauses = ["access_scope = 'public'"]
        values: list[Any] = []
        if game_id:
            clauses.append("game_id = ?")
            values.append(game_id)
        if relevance_label:
            clauses.append("relevance_label = ?")
            values.append(relevance_label)
        if community_only:
            placeholders = ",".join("?" for _ in COMMUNITY_KINDS)
            clauses.append(f"evidence_kind IN ({placeholders})")
            values.extend(sorted(COMMUNITY_KINDS))
        return self._query(" AND ".join(clauses), values)

    def query_relevant_ugc(self, game_id: str) -> list[EvidenceItem]:
        return self.query_public(game_id=game_id, relevance_label="relevant", community_only=True)

    def query_ambiguous(self, game_id: str | None = None) -> list[EvidenceItem]:
        return self.query_public(game_id=game_id, relevance_label="ambiguous", community_only=True)

    def query_private(
        self,
        *,
        dataset_id: str,
        owner_scope: str,
        game_id: str | None = None,
    ) -> list[EvidenceItem]:
        with self._connection() as connection:
            self._validate_private_scope(connection, dataset_id=dataset_id, owner_scope=owner_scope)
        clauses = ["access_scope = 'private'", "dataset_id = ?", "owner_scope = ?"]
        values: list[Any] = [dataset_id, owner_scope]
        if game_id:
            clauses.append("game_id = ?")
            values.append(game_id)
        return self._query(" AND ".join(clauses), values)

    def get_evidence(
        self,
        evidence_id: str,
        *,
        dataset_id: str | None = None,
        owner_scope: str | None = None,
    ) -> EvidenceItem | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            if row is None:
                return None
            if row["access_scope"] == "private":
                if not dataset_id or not owner_scope:
                    raise PermissionError("private evidence requires dataset_id and owner_scope")
                self._validate_private_scope(connection, dataset_id=dataset_id, owner_scope=owner_scope)
                if row["dataset_id"] != dataset_id or row["owner_scope"] != owner_scope:
                    raise PermissionError("private evidence scope does not match")
            return self._hydrate(connection, row)

    def duplicate_info(self, evidence_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT identity_key, content_fingerprint FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            if not row:
                return None
            matches = connection.execute(
                """
                SELECT evidence_id, source FROM evidence
                WHERE content_fingerprint = ? AND evidence_id != ?
                ORDER BY evidence_id
                """,
                (row["content_fingerprint"], evidence_id),
            ).fetchall()
        return {
            "content_fingerprint": row["content_fingerprint"],
            "likely_cross_posts": [dict(match) for match in matches],
        }

    def count(self, *, access_scope: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM evidence"
        values: tuple[Any, ...] = ()
        if access_scope:
            query += " WHERE access_scope = ?"
            values = (access_scope,)
        with self._connection() as connection:
            return int(connection.execute(query, values).fetchone()["count"])

    def _query(self, where: str, values: list[Any]) -> list[EvidenceItem]:
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM evidence WHERE {where} ORDER BY evidence_id",
                values,
            ).fetchall()
            return [self._hydrate(connection, row) for row in rows]

    @staticmethod
    def _hydrate(connection: sqlite3.Connection, row: sqlite3.Row) -> EvidenceItem:
        item = EvidenceItem.model_validate_json(row["payload_json"])
        links = connection.execute(
            """
            SELECT query_id, run_id, source, language, intent, query_text, alias_ids_json
            FROM evidence_query_links WHERE evidence_id = ? ORDER BY query_id
            """,
            (row["evidence_id"],),
        ).fetchall()
        if not links:
            return item
        matched_queries = []
        alias_ids = set(item.matched_alias_ids)
        for link in links:
            link_aliases = json.loads(link["alias_ids_json"])
            alias_ids.update(link_aliases)
            matched_queries.append(
                {
                    "query_id": link["query_id"],
                    "run_id": link["run_id"],
                    "source": link["source"],
                    "language": link["language"],
                    "intent": link["intent"],
                    "query_text": link["query_text"],
                    "alias_ids": link_aliases,
                }
            )
        metadata = dict(item.source_metadata)
        metadata["matched_queries"] = matched_queries
        return item.model_copy(
            update={"matched_alias_ids": sorted(alias_ids), "source_metadata": metadata}
        )
