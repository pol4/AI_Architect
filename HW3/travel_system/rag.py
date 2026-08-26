from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any

from .state import PolicyChunk, PolicyDecision, TripRequest

# Демонстрационные документы; в production источник — корпоративное хранилище.
DEFAULT_POLICIES = [
    ("TRAVEL-001", "2026.1", "Обязательные данные", "Для командировки нужны город отправления, пункт назначения, даты выезда и возвращения, цель поездки и бюджет.", "2026-01-01"),
    ("TRAVEL-002", "2026.1", "Согласование", "Поездка с бюджетом свыше 100000 рублей требует согласования руководителя и финансового контролёра.", "2026-01-01"),
    ("TRAVEL-003", "2026.1", "Состав услуг", "Для международной поездки нужно проверить необходимость визы и медицинской страховки. Для поездки более чем на 50 километров от аэропорта можно подобрать трансфер.", "2026-01-01"),
]


def tokenize(value: str) -> set[str]:
    tokens = (token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", value))
    return {re.sub(r"(ами|ями|ого|ему|ому|ыми|ими|ов|ев|ы|и|а|я|е|у|ю)$", "", token) for token in tokens}


class PolicyRAG:
    # RAG-контур: ingestion нормативных документов и runtime retrieval.
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_store()

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_store(self) -> None:
        connection = self._connection()
        connection.execute("CREATE TABLE IF NOT EXISTS policy_documents (policy_id TEXT PRIMARY KEY, version TEXT, title TEXT, text TEXT, status TEXT, effective_from TEXT, effective_to TEXT, source_uri TEXT)")
        connection.execute("CREATE TABLE IF NOT EXISTS policy_chunks (chunk_id TEXT PRIMARY KEY, policy_id TEXT, version TEXT, text TEXT, citation TEXT, effective_from TEXT, effective_to TEXT, scope TEXT, content_hash TEXT, embedding TEXT, status TEXT)")
        for policy_id, version, title, text, effective_from in DEFAULT_POLICIES:
            connection.execute("INSERT OR IGNORE INTO policy_documents VALUES(?,?,?,?,?,?,?,?)", (policy_id, version, title, text, "published", effective_from, None, "demo://corporate-policy"))
            self._index_document(connection, policy_id, version, title, text, effective_from, None)
        connection.commit()
        connection.close()

    def _index_document(self, connection: sqlite3.Connection, policy_id: str, version: str, title: str, text: str, effective_from: str, effective_to: str | None) -> None:
        chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        for index, chunk in enumerate(chunks):
            chunk_id = f"{policy_id}:{version}:{index}"
            content_hash = hashlib.sha256(chunk.encode()).hexdigest()
            connection.execute("INSERT OR REPLACE INTO policy_chunks VALUES(?,?,?,?,?,?,?,?,?,?,?)", (chunk_id, policy_id, version, chunk, f"{title}, пункт {index + 1}", effective_from, effective_to, "{}", content_hash, "", "published"))

    def ingest(self, document: dict[str, Any]) -> dict[str, Any]:
        required = ("policy_id", "version", "title", "text")
        if any(not str(document.get(field, "")).strip() for field in required):
            raise ValueError("policy_id, version, title and text are required")
        connection = self._connection()
        policy_id = document["policy_id"]
        version = document["version"]
        effective_from = document.get("effective_from", "2026-01-01")
        effective_to = document.get("effective_to")
        connection.execute("UPDATE policy_documents SET status='archived' WHERE policy_id=?", (policy_id,))
        connection.execute("INSERT OR REPLACE INTO policy_documents VALUES(?,?,?,?,?,?,?,?)", (policy_id, version, document["title"], document["text"], "published", effective_from, effective_to, document.get("source_uri", "api://policy")))
        self._index_document(connection, policy_id, version, document["title"], document["text"], effective_from, effective_to)
        connection.commit()
        connection.close()
        return {"policy_id": policy_id, "version": version, "status": "published", "chunks_count": len(re.split(r"(?<=[.!?])\s+", document["text"]))}

    def retrieve(self, trip: TripRequest) -> list[PolicyChunk]:
        query = tokenize(" ".join(str(value) for value in trip.values() if value))
        destination = str(trip.get("destination") or "").strip().lower()
        domestic_destinations = {"москва", "санкт-петербург", "екатеринбург", "казань", "новосибирск"}
        international = bool(destination) and destination not in domestic_destinations
        connection = self._connection()
        rows = connection.execute("SELECT * FROM policy_chunks WHERE status='published'").fetchall()
        connection.close()
        scored = []
        for row in rows:
            if row["policy_id"] == "TRAVEL-003" and not international:
                continue
            policy_tokens = tokenize(row["text"])
            overlap = len(query & policy_tokens)
            normalized_overlap = sum(1 for query_token in query if any(query_token in policy_token or policy_token in query_token for policy_token in policy_tokens))
            overlap = max(overlap, normalized_overlap)
            if row["policy_id"] in {"TRAVEL-001", "TRAVEL-002"}:
                overlap += 1
            if overlap:
                scored.append((overlap, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [{"policy_id": row["policy_id"], "version": row["version"], "chunk_id": row["chunk_id"], "text": row["text"], "citation": row["citation"], "effective_from": row["effective_from"], "effective_to": row["effective_to"], "scope": {}, "content_hash": row["content_hash"]} for _, row in scored]

    def evaluate(self, trip: TripRequest, context: list[PolicyChunk]) -> list[PolicyDecision]:
        decisions: list[PolicyDecision] = []
        budget = float(trip.get("budget") or 0)
        for chunk in context:
            if chunk["policy_id"] == "TRAVEL-002":
                decision = "conditional" if budget > 100000 else "allowed"
                decisions.append({"decision": decision, "policy_refs": [chunk["policy_id"]], "citations": [chunk["citation"]], "rule_code": "BUDGET_APPROVAL", "evaluated_values": {"budget": budget, "threshold": 100000}, "explanation": "Согласование требуется при превышении лимита 100000 рублей."})
            elif chunk["policy_id"] == "TRAVEL-003":
                decisions.append({"decision": "conditional", "policy_refs": [chunk["policy_id"]], "citations": [chunk["citation"]], "rule_code": "INTERNATIONAL_DOCUMENTS", "evaluated_values": {"destination": trip.get("destination")}, "explanation": "Проверить визу и медицинскую страховку для международной поездки."})
        return decisions
