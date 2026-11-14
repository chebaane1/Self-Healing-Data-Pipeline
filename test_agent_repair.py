import tempfile
import unittest
from pathlib import Path

import duckdb

from agent_repair import (
    INIT_SOURCE_PATH,
    RepairTools,
    identify_repair_target,
    is_resource_failure,
    read_duckdb_schema,
)


class RepairToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "models" / "staging").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / "data").mkdir()
        (self.root / "models" / "staging" / "stg_orders.sql").write_text(
            "select 1\n", encoding="utf-8"
        )
        (self.root / "models" / "schema.yml").write_text(
            "version: 2\n", encoding="utf-8"
        )
        (self.root / "models" / "staging" / "sources.yml").write_text(
            "version: 2\n", encoding="utf-8"
        )
        (self.root / INIT_SOURCE_PATH).write_text(
            "print('source')\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_only_allowed_metadata_can_be_written(self):
        tools = RepairTools(self.root, "models/staging/stg_orders.sql", 1)

        tools.write_project_file("models/schema.yml", "version: 2\nmodels: []")
        with self.assertRaises(ValueError):
            tools.write_project_file("scripts/init_source.py", "raise SystemExit")
        with self.assertRaises(ValueError):
            tools.write_project_file("README.md", "changed")
        with self.assertRaises(ValueError):
            tools.read_project_file("../outside.txt")

    def test_ingestion_edit_requires_resource_failure_permission(self):
        tools = RepairTools(
            self.root,
            "models/staging/stg_orders.sql",
            1,
            allow_ingestion_edits=True,
        )

        tools.write_project_file(INIT_SOURCE_PATH, "print('batched')")
        self.assertIn("batched", tools.read_project_file(INIT_SOURCE_PATH))

    def test_resource_failure_detection_and_target_routing(self):
        self.assertTrue(is_resource_failure("DuckDB Out of Memory Error"))
        self.assertTrue(is_resource_failure("validation timed out"))
        self.assertFalse(is_resource_failure("column amount does not exist"))

        target, is_sql_model = identify_repair_target(
            "Failed command: python scripts/init_source.py\nMemoryError",
            self.root,
        )
        self.assertEqual(target, self.root / INIT_SOURCE_PATH)
        self.assertFalse(is_sql_model)

        target, is_sql_model = identify_repair_target(
            "Error loading models/staging/sources.yml", self.root
        )
        self.assertEqual(target, self.root / "models" / "staging" / "sources.yml")
        self.assertFalse(is_sql_model)

    def test_duckdb_schema_is_read_from_database(self):
        database_path = self.root / "data" / "pipeline.duckdb"
        connection = duckdb.connect(str(database_path))
        connection.execute("CREATE TABLE raw_orders (order_id INTEGER, amount VARCHAR)")
        connection.close()

        schema = read_duckdb_schema(self.root)

        self.assertIn('"column": "order_id"', schema)
        self.assertIn('"type": "VARCHAR"', schema)


if __name__ == "__main__":
    unittest.main()