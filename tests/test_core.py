import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest

from querypilot.__main__ import build_demo_database, demo_policy
from querypilot.core import SQLiteTools, run_agent


class QueryPilotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "shop.sqlite"
        build_demo_database(self.database)
        self.tools = SQLiteTools(self.database)

    def tearDown(self):
        self.directory.cleanup()

    def test_agent_observes_error_and_self_corrects(self):
        result = run_agent(demo_policy, "哪种商品的销售额最高？", self.tools)
        self.assertEqual(result["answer"], "销售额最高的是积木，销售额为240元。")
        sql_steps = [x for x in result["trace"] if x.get("name") == "execute_sql"]
        self.assertFalse(sql_steps[0]["observation"]["ok"])
        self.assertTrue(sql_steps[1]["observation"]["ok"])

    def test_database_is_read_only(self):
        with self.assertRaises(ValueError):
            self.tools.execute_sql("DELETE FROM orders")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 4)

    def test_invalid_tool_and_budget_are_rejected(self):
        with self.assertRaises(ValueError):
            self.tools.call("shell", {"command": "whoami"})
        looping = lambda messages, schemas: {"type": "tool", "name": "list_tables", "arguments": {}}
        with self.assertRaisesRegex(RuntimeError, "step budget"):
            run_agent(looping, "loop", self.tools, max_steps=2)


if __name__ == "__main__":
    unittest.main()
