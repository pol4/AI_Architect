from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class LLMGateway:
    # Единая фабрика OpenAI-compatible клиентов для ролей моделей.
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def _settings(self, role: str) -> tuple[str, str, str]:
        connection = sqlite3.connect(self.db_path)
        row = connection.execute("SELECT base_url, api_key, model FROM settings WHERE role=?", (role,)).fetchone()
        connection.close()
        return row if row else ("https://api.openai.com/v1", "", "gpt-4o-mini")

    # Возвращает клиент только при наличии сохранённого API key.
    def client(self, role: str) -> ChatOpenAI | None:
        base_url, api_key, model = self._settings(role)
        if not api_key:
            return None
        return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0)

    def invoke_json(self, role: str, system: str, prompt: str) -> dict[str, Any] | None:
        client = self.client(role)
        if client is None:
            return None
        response = client.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else json.dumps(response.content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    async def ainvoke_json(self, role: str, system: str, prompt: str) -> dict[str, Any] | None:
        client = self.client(role)
        if client is None:
            return None
        response = await client.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else json.dumps(response.content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
