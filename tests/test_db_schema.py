"""Tests para el esquema de base de datos PostgreSQL (db/init.sql - Issues #7 y #8)."""

from pathlib import Path
import re
import unittest
from uuid import uuid4

import psycopg

from common.config import load_config

ROOT_DIR = Path(__file__).resolve().parent.parent
INIT_SQL_PATH = ROOT_DIR / "db" / "init.sql"
COMPOSE_PATH = ROOT_DIR / "docker-compose.yml"


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


class TestDockerComposeAndLivePostgres(unittest.TestCase):
    """Ciclo 7 TDD: Servicios postgres y redis en compose (#9) y validación real de constraints (#7, #8)."""

    def test_docker_compose_defines_postgres_and_redis_with_healthchecks(self) -> None:
        self.assertTrue(
            COMPOSE_PATH.is_file(),
            "El archivo docker-compose.yml no existe.",
        )
        content = COMPOSE_PATH.read_text(encoding="utf-8")

        self.assertIn("postgres:18.4-bookworm", content)
        self.assertIn("pgdata:", content)
        self.assertIn("init.sql", content)
        self.assertIn("allkeys-lru", content)
        self.assertIn("maxmemory", content)
        self.assertIn("healthcheck:", content)

    def test_postgres_enforces_unique_username_and_valid_video_status(self) -> None:
        cfg = load_config()
        with psycopg.connect(cfg.db_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                # Ejecutar transacción con rollback al final para no ensuciar la BD de dev
                unique_user = f"test_u_{uuid4().hex[:10]}"
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                    (unique_user, "scrypt$hash"),
                )
                user_row = cur.fetchone()
                self.assertIsNotNone(user_row)
                user_id = user_row[0]

                # 1. Criterio Issue #7: Insertar username duplicado falla por restricción UNIQUE
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    with conn.transaction():
                        cur.execute(
                            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                            (unique_user, "other_hash"),
                        )

                # 2. Criterio Issue #8: status solo acepta los valores permitidos
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                uuid4(),
                                user_id,
                                "Video invalido",
                                "test.mp4",
                                "/data/videos/test.mp4",
                                1024,
                                "estado_invalido",
                            ),
                        )

                # 3. Criterio Issue #8: Existe índice sobre status
                cur.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'videos' AND indexdef ILIKE '%(status)%'"
                )
                idx_row = cur.fetchone()
                self.assertIsNotNone(idx_row)

            conn.rollback()


if __name__ == "__main__":
    unittest.main()
