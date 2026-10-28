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
    """Ciclo 5 TDD: Definición de la tabla `users` y `videos` en db/init.sql (Issues #7 y #8)."""

    def test_init_sql_defines_users_table_with_unique_username_and_checks(self) -> None:
        self.assertTrue(
            INIT_SQL_PATH.is_file(),
            "El archivo db/init.sql no existe.",
        )
        sql_content = INIT_SQL_PATH.read_text(encoding="utf-8")

        self.assertRegex(
            sql_content,
            re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?users\b", re.IGNORECASE),
        )
        # Evitar falsos positivos de substring usando límites de palabra (\b)
        for required_col in ("id", "username", "password_hash", "created_at"):
            with self.subTest(column=required_col):
                self.assertRegex(
                    sql_content,
                    re.compile(rf"\b{re.escape(required_col)}\b", re.IGNORECASE),
                )

        self.assertRegex(
            sql_content,
            re.compile(r"username\s+VARCHAR\(\d+\)\s+NOT\s+NULL\s+UNIQUE", re.IGNORECASE),
        )
        self.assertRegex(
            sql_content,
            re.compile(r"length\(btrim\(username\)\)\s*>=\s*3", re.IGNORECASE),
        )

    def test_init_sql_defines_videos_table_check_status_unique_path_and_index(self) -> None:
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
                self.assertRegex(
                    sql_content,
                    re.compile(rf"\b{re.escape(col)}\b", re.IGNORECASE),
                )

        # path debe ser UNIQUE y no vacío
        self.assertRegex(
            sql_content,
            re.compile(r"path\s+TEXT\s+NOT\s+NULL\s+UNIQUE", re.IGNORECASE),
        )

        # Restricciones de no-negatividad
        self.assertRegex(sql_content, re.compile(r"duration_s\s+.*?CHECK\s*\(\s*duration_s\s*>=\s*0", re.IGNORECASE))
        self.assertRegex(sql_content, re.compile(r"width\s+.*?CHECK\s*\(\s*width\s*>=\s*0", re.IGNORECASE))
        self.assertRegex(sql_content, re.compile(r"height\s+.*?CHECK\s*\(\s*height\s*>=\s*0", re.IGNORECASE))

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
    """Ciclo 7 TDD: Servicios compose y validación real de constraints en PostgreSQL (#7, #8, #9)."""

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

    def test_postgres_enforces_schema_constraints_and_cascade(self) -> None:
        cfg = load_config()
        try:
            conn = psycopg.connect(cfg.db_url, connect_timeout=3)
        except (psycopg.OperationalError, psycopg.DatabaseError) as exc:
            self.skipTest(f"PostgreSQL no está disponible en {cfg.db_url}: {exc}")

        with conn:
            with conn.cursor() as cur:
                # 1. Crear usuario válido
                unique_user = f"test_u_{uuid4().hex[:10]}"
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                    (unique_user, "scrypt$hash"),
                )
                user_id = cur.fetchone()[0]

                # 2. Restricción UNIQUE en username
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    with conn.transaction():
                        cur.execute(
                            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                            (unique_user, "other_hash"),
                        )

                # 3. Restricción CHECK de username no blanco / mínimo 3 caracteres
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with conn.transaction():
                        cur.execute(
                            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                            ("  ab  ", "other_hash"),
                        )

                # 4. Insertar video válido
                video_id = uuid4()
                unique_path = f"/data/videos/{video_id}.mp4"
                cur.execute(
                    """
                    INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes, duration_s, width, height, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        video_id,
                        user_id,
                        "Video valido",
                        "test.mp4",
                        unique_path,
                        1024,
                        12.5,
                        1280,
                        720,
                        "uploading",
                    ),
                )

                # 5. Restricción UNIQUE en path de video
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (uuid4(), user_id, "Otro video", "otro.mp4", unique_path, 2048),
                        )

                # 6. Restricción CHECK de status permitido
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (uuid4(), user_id, "Video invalido", "test.mp4", f"/data/videos/{uuid4()}.mp4", 1024, "invalido"),
                        )

                # 7. Restricción CHECK de size_bytes > 0
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (uuid4(), user_id, "Video zero bytes", "test.mp4", f"/data/videos/{uuid4()}.mp4", 0),
                        )

                # 8. Restricción CHECK de no-negatividad en duration, width, height
                for bad_dim in ({"duration_s": -1.0}, {"width": -1}, {"height": -1}):
                    with self.subTest(bad_dim=bad_dim):
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            with conn.transaction():
                                cur.execute(
                                    f"""
                                    INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes, {list(bad_dim.keys())[0]})
                                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                                    """,
                                    (uuid4(), user_id, "Video neg", "test.mp4", f"/data/videos/{uuid4()}.mp4", 1024, list(bad_dim.values())[0]),
                                )

                # 9. FK Violation: owner_id inexistente
                with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                    with conn.transaction():
                        cur.execute(
                            """
                            INSERT INTO videos (id, owner_id, title, original_filename, path, size_bytes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (uuid4(), 999999, "Video sin owner", "test.mp4", f"/data/videos/{uuid4()}.mp4", 1024),
                        )

                # 10. ON DELETE CASCADE: borrar usuario borra sus videos
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                cur.execute("SELECT COUNT(*) FROM videos WHERE id = %s", (video_id,))
                self.assertEqual(cur.fetchone()[0], 0)

                # 11. Índice sobre status existe
                cur.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'videos' AND indexdef ILIKE '%(status)%'"
                )
                self.assertIsNotNone(cur.fetchone())

            conn.rollback()


if __name__ == "__main__":
    unittest.main()

