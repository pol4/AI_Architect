from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from langgraph.types import Command

from travel_system.graphs import TravelGraphs
from travel_system.rag import PolicyRAG

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DB_PATH = Path(os.getenv("TRAVEL_DB_PATH", ROOT / "travel.db"))
HOST = os.getenv("TRAVEL_HOST", "127.0.0.1")
PORT = int(os.getenv("TRAVEL_PORT", "8080"))
ROLES = ("parser", "supervisor", "worker", "summary")


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    connection = database()
    connection.execute("CREATE TABLE IF NOT EXISTS settings (role TEXT PRIMARY KEY, provider TEXT NOT NULL, base_url TEXT NOT NULL, api_key TEXT NOT NULL DEFAULT '', model TEXT NOT NULL, updated_at TEXT NOT NULL)")
    defaults = {role: ("openai", "https://api.openai.com/v1", "gpt-4o-mini") for role in ROLES}
    for role, (provider, base_url, model) in defaults.items():
        connection.execute("INSERT OR IGNORE INTO settings VALUES(?,?,?,?,?,datetime('now'))", (role, provider, base_url, "", model))
    connection.commit()
    connection.close()


def settings_public() -> dict:
    connection = database()
    rows = connection.execute("SELECT role, provider, base_url, model, api_key, updated_at FROM settings").fetchall()
    connection.close()
    return {row["role"]: {"provider": row["provider"], "base_url": row["base_url"], "model": row["model"], "configured": bool(row["api_key"]), "updated_at": row["updated_at"]} for row in rows}


def save_settings(payload: dict) -> dict:
    connection = database()
    for role in ROLES:
        item = payload.get(role, {})
        if not isinstance(item, dict):
            continue
        values = (str(item.get("provider", "openai")), str(item.get("base_url", "https://api.openai.com/v1")).rstrip("/"), str(item.get("model", "gpt-4o-mini")))
        if item.get("api_key"):
            connection.execute("UPDATE settings SET provider=?, base_url=?, model=?, api_key=?, updated_at=datetime('now') WHERE role=?", (*values, str(item["api_key"]), role))
        else:
            connection.execute("UPDATE settings SET provider=?, base_url=?, model=?, updated_at=datetime('now') WHERE role=?", (*values, role))
    connection.commit()
    connection.close()
    return settings_public()


# Графы создаются лениво после инициализации persistent policy store.
def load_workflow() -> TravelGraphs:
    return TravelGraphs(PolicyRAG(DB_PATH))


WORKFLOW = None


def workflow() -> TravelGraphs:
    global WORKFLOW
    if WORKFLOW is None:
        WORKFLOW = load_workflow()
    return WORKFLOW


def config(case_id: str) -> dict:
    return {"configurable": {"thread_id": case_id}}


def current_state(case_id: str) -> dict:
    snapshot = workflow().trip_graph.get_state(config(case_id))
    return dict(snapshot.values) if snapshot else {}


def run_trip(case_id: str, request_text: str | None = None, resume: dict | None = None) -> dict:
    if resume is None:
        workflow().trip_graph.invoke({"case_id": case_id, "request_text": request_text or "", "user_id": "demo-user", "audit": []}, config(case_id))
    else:
        workflow().trip_graph.invoke(Command(resume=resume), config(case_id))
    return current_state(case_id)


# HTTP-адаптер не содержит бизнес-правил и делегирует их LangGraph.
class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode() or "{}")

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json(200, {"status": "ok", "langgraph": True})
            return
        if self.path == "/api/config":
            self.send_json(200, {"roles": settings_public()})
            return
        if self.path == "/api/policies":
            connection = database()
            rows = connection.execute("SELECT policy_id, version, title, text, status FROM policy_documents ORDER BY policy_id").fetchall()
            connection.close()
            self.send_json(200, {"policies": [dict(row) for row in rows]})
            return
        if self.path.startswith("/api/trips/"):
            self.send_json(200, current_state(self.path.rsplit("/", 1)[-1]))
            return
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            content = (STATIC_DIR / "index.html").read_bytes()
        elif self.path.split("?", 1)[0] == "/approval.html":
            content = (STATIC_DIR / "approval.html").read_bytes()
        else:
            self.send_json(404, {"error": "Not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        try:
            payload = self.read_body()
            if self.path == "/api/config":
                self.send_json(200, {"roles": save_settings(payload.get("roles", payload))})
                return
            if self.path == "/api/policies":
                result = workflow().rag.ingest(payload)
                self.send_json(201, result)
                return
            if self.path == "/api/trips":
                request_text = str(payload.get("request_text", "")).strip()
                if len(request_text) < 10:
                    self.send_json(400, {"error": "Опишите командировку подробнее"})
                    return
                import uuid
                case_id = f"case_{uuid.uuid4().hex[:12]}"
                self.send_json(200, run_trip(case_id, request_text=request_text))
                return
            parts = self.path.strip("/").split("/")
            if len(parts) == 4 and parts[0:2] == ["api", "trips"]:
                case_id, action = parts[2], parts[3]
                if action == "answers":
                    result = run_trip(case_id, resume=payload.get("answers", payload))
                elif action == "approval":
                    result = run_trip(case_id, resume={"decision": payload.get("decision"), "comment": payload.get("comment", "")})
                elif action == "replan":
                    result = workflow().replanning_graph.invoke({**current_state(case_id), "replan_reason": payload.get("reason", "unavailable")}, config(case_id))
                elif action == "selection":
                    result = workflow().booking_graph.invoke({**current_state(case_id), "selected_alternative_id": payload.get("alternative_id")}, config(case_id))
                elif action == "cancel":
                    result = workflow().cancellation_graph.invoke({**current_state(case_id), "bookings": current_state(case_id).get("bookings", []), "cancel_confirmed": bool(payload.get("confirm"))}, config(case_id))
                else:
                    self.send_json(404, {"error": "Not found"})
                    return
                self.send_json(202, dict(result))
                return
            self.send_json(404, {"error": "Not found"})
        except Exception as error:
            self.send_json(500, {"error": str(error)})

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Travel automation UI: http://{HOST}:{PORT}")
    server.serve_forever()
