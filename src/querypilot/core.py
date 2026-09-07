"""Small agent loop and read-only SQLite tools."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

Policy = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]

SYSTEM_PROMPT = """You are a data assistant. Use the available tools to inspect the
database and answer the user's question from query results. Never invent tables,
columns, or values. Return a final answer only after obtaining enough evidence."""

TOOL_SCHEMAS = [
    {"name": "list_tables", "description": "List user tables.", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_schema", "description": "Inspect columns for one or more tables.", "parameters": {
        "type": "object", "properties": {"table_names": {"type": "array", "items": {"type": "string"}}},
        "required": ["table_names"]}},
    {"name": "execute_sql", "description": "Execute one read-only SQL query.", "parameters": {
        "type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}},
]


class SQLiteTools:
    """Three bounded tools over an existing SQLite database."""

    def __init__(self, database: str | Path, row_limit: int = 20, timeout_seconds: float = 2.0):
        self.database = Path(database).resolve()
        if not self.database.is_file():
            raise FileNotFoundError(self.database)
        self.row_limit = row_limit
        self.timeout_seconds = timeout_seconds

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        deadline = time.monotonic() + self.timeout_seconds
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1_000)
        return connection

    def list_tables(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return {"tables": [row[0] for row in rows]}

    def get_schema(self, table_names: Any) -> dict[str, Any]:
        if not isinstance(table_names, list) or not table_names or not all(isinstance(x, str) for x in table_names):
            raise ValueError("table_names must be a non-empty list of strings")
        available = set(self.list_tables()["tables"])
        unknown = sorted(set(table_names) - available)
        if unknown:
            raise ValueError(f"unknown tables: {unknown}")
        schemas: dict[str, list[dict[str, Any]]] = {}
        with closing(self._connect()) as connection:
            for table in table_names:
                quoted = table.replace('"', '""')
                rows = connection.execute(f'PRAGMA table_info("{quoted}")').fetchall()
                schemas[table] = [
                    {"name": row[1], "type": row[2], "nullable": not bool(row[3]), "primary_key": bool(row[5])}
                    for row in rows
                ]
        return {"schemas": schemas}

    def execute_sql(self, sql: Any) -> dict[str, Any]:
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 10_000:
            raise ValueError("sql must be a non-empty string of at most 10000 characters")
        first_word = sql.lstrip().split(None, 1)[0].upper()
        if first_word not in {"SELECT", "WITH"}:
            raise ValueError("only SELECT or WITH queries are allowed")
        with closing(self._connect()) as connection:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(self.row_limit + 1)
            columns = [item[0] for item in cursor.description or []]
        truncated = len(rows) > self.row_limit
        return {
            "columns": columns,
            "rows": [[_json_value(value) for value in row] for row in rows[: self.row_limit]],
            "truncated": truncated,
        }

    def call(self, name: Any, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if name == "list_tables" and not arguments:
            return self.list_tables()
        if name == "get_schema" and set(arguments) == {"table_names"}:
            return self.get_schema(arguments["table_names"])
        if name == "execute_sql" and set(arguments) == {"sql"}:
            return self.execute_sql(arguments["sql"])
        raise ValueError("unknown tool or invalid arguments")


def run_agent(policy: Policy, question: str, tools: SQLiteTools, max_steps: int = 8) -> dict[str, Any]:
    """Run one bounded agent episode and return its answer plus full trace."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question.strip()},
    ]
    trace: list[dict[str, Any]] = []
    for step in range(1, max_steps + 1):
        action = policy(messages, TOOL_SCHEMAS)
        if not isinstance(action, dict) or action.get("type") not in {"tool", "final"}:
            raise ValueError("policy must return a tool or final action")
        if action["type"] == "final":
            answer = action.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("final answer must be non-empty")
            trace.append({"step": step, "type": "final", "answer": answer.strip()})
            return {"answer": answer.strip(), "trace": trace, "steps": step}

        name, arguments = action.get("name"), action.get("arguments")
        try:
            observation = {"ok": True, "result": tools.call(name, arguments)}
        except (ValueError, sqlite3.Error) as error:
            observation = {"ok": False, "error": str(error)}
        trace.append({"step": step, "type": "tool", "name": name, "arguments": arguments, "observation": observation})
        messages.extend([
            {"role": "assistant", "tool_call": {"name": name, "arguments": arguments}},
            {"role": "tool", "name": name, "content": json.dumps(observation, ensure_ascii=False)},
        ])
    raise RuntimeError(f"agent exceeded the {max_steps}-step budget")


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value
