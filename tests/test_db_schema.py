"""Tests para el esquema de base de datos PostgreSQL (db/init.sql - Issues #7 y #8)."""

from pathlib import Path
import re
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
INIT_SQL_PATH = ROOT_DIR / "db" / "init.sql"


class TestDatabaseSchemaUsers(unittest.TestCase):
    """Ciclo 5 TDD: Definición de la tabla `users` en db/init.sql (Issue #7)."""

    def test_init_sql_defines_users_table_with_unique_username(self) -> None:
        self.assertTrue(
            INIT_SQL_PATH.is_file(),
            "El archivo db/init.sql no existe.",
        )
        sql_content = INIT_SQL_PATH.read_text(encoding="utf-8")

        self.assertRegex(
            sql_content,
            re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?users\b", re.IGNORECASE),
        )
        for required_col in ("id", "username", "password_hash", "created_at"):
            with self.subTest(column=required_col):
                self.assertIn(required_col, sql_content)

        self.assertRegex(
            sql_content,
            re.compile(r"username\s+VARCHAR\(\d+\)\s+NOT\s+NULL\s+UNIQUE", re.IGNORECASE),
        )


if __name__ == "__main__":
    unittest.main()
