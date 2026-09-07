"""Run the deterministic smoke demo: python -m querypilot --demo."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from .core import SQLiteTools, run_agent


def build_demo_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL
            );
            INSERT INTO products VALUES (1, '积木'), (2, '绘本'), (3, '画笔');
            INSERT INTO orders VALUES
                (1, 1, 2, 80.0), (2, 2, 6, 35.0), (3, 3, 4, 25.0), (4, 1, 1, 80.0);
        """)
        connection.commit()


def demo_policy(messages, schemas):
    """Scripted policy that deliberately makes and repairs one SQL error."""
    observations = [json.loads(item["content"]) for item in messages if item["role"] == "tool"]
    if not observations:
        return {"type": "tool", "name": "list_tables", "arguments": {}}
    if len(observations) == 1:
        return {"type": "tool", "name": "get_schema", "arguments": {"table_names": ["products", "orders"]}}
    if len(observations) == 2:
        return {"type": "tool", "name": "execute_sql", "arguments": {"sql":
            "SELECT p.name, SUM(o.quantity * o.price) AS revenue FROM orders o "
            "JOIN products p ON p.id=o.product_id GROUP BY p.id ORDER BY revenue DESC LIMIT 1"}}
    if not observations[-1]["ok"]:
        return {"type": "tool", "name": "execute_sql", "arguments": {"sql":
            "SELECT p.name, SUM(o.quantity * o.unit_price) AS revenue FROM orders o "
            "JOIN products p ON p.id=o.product_id GROUP BY p.id ORDER BY revenue DESC LIMIT 1"}}
    row = observations[-1]["result"]["rows"][0]
    return {"type": "final", "answer": f"销售额最高的是{row[0]}，销售额为{row[1]:.0f}元。"}


def main() -> None:
    parser = argparse.ArgumentParser(description="QueryPilot minimal runtime")
    parser.add_argument("--demo", action="store_true", help="run the deterministic smoke demo")
    args = parser.parse_args()
    if not args.demo:
        parser.error("the first version only exposes --demo; a real model provider is the next milestone")
    with tempfile.TemporaryDirectory(prefix="querypilot-") as directory:
        database = Path(directory) / "shop.sqlite"
        build_demo_database(database)
        result = run_agent(demo_policy, "哪种商品的销售额最高？", SQLiteTools(database))
    for event in result["trace"]:
        print(json.dumps(event, ensure_ascii=False))
    print("ANSWER:", result["answer"])


if __name__ == "__main__":
    main()
