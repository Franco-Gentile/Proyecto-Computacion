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

    def test_init_sql_defines_videos_table_check_status_and_index(self) -> None:
        sql_content = INIT_SQL_PATH.read_text(encoding="utf-8")

        self.assertRegex(
            sql_content,
            re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?videos\b", re.IGNORECASE),
        )
        required_columns = (
            "id",
            "owner_id",
            "title",
            "original_filename",
            "path",
            "size_bytes",
            "duration_s",
            "width",
            "height",
            "status",
            "created_at",
        )
        for col in required_columns:
            with self.subTest(column=col):
                self.assertIn(col, sql_content)

        # Restricción CHECK de estados permitidos
        for allowed_status in ("'uploading'", "'processing'", "'ready'", "'error'"):
            with self.subTest(status=allowed_status):
                self.assertIn(allowed_status, sql_content)

        # Índice sobre la columna status
        self.assertRegex(
            sql_content,
            re.compile(
                r"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+videos\s*\(\s*status\s*\)",
                re.IGNORECASE,
            ),
        )


if __name__ == "__main__":
    unittest.main()
