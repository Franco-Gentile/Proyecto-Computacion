"""Tests unitarios para el módulo de configuración (common/config.py - Issue #5)."""

import unittest

from common.config import AppConfig, ConfigError, load_config
from common.domain.enums import Quality


class TestLoadConfigDefaults(unittest.TestCase):
    """Ciclo 1 TDD: una variable faltante usa su valor por defecto de dev."""

    def test_load_config_uses_defaults_when_env_is_empty(self) -> None:
        cfg = load_config({})

        self.assertIsInstance(cfg, AppConfig)
        # Base de datos (PostgreSQL 18.4-bookworm en puerto 5434)
        self.assertEqual(cfg.db_host, "localhost")
        self.assertEqual(cfg.db_port, 5434)
        self.assertEqual(cfg.db_name, "videoapp_dev")
        self.assertEqual(cfg.db_username, "videoapp")
        self.assertEqual(cfg.db_password, "videoapp_dev_pass")
        self.assertEqual(
            cfg.db_url,
            "postgresql://videoapp:videoapp_dev_pass@localhost:5434/videoapp_dev",
        )

        # Redis
        self.assertEqual(cfg.redis_host, "localhost")
        self.assertEqual(cfg.redis_port, 6379)
        self.assertEqual(cfg.redis_url, "redis://localhost:6379/0")

        # Servidor TCP
        self.assertEqual(cfg.server_host, "0.0.0.0")
        self.assertEqual(cfg.server_port, 9000)
        self.assertEqual(cfg.max_clients, 50)

        # Videos y Streaming
        self.assertEqual(cfg.videos_dir, "/data/videos")
        self.assertEqual(cfg.max_upload_mb, 500)
        self.assertEqual(cfg.max_upload_bytes, 500 * 1024 * 1024)
        self.assertEqual(cfg.seg_len, 4)
        self.assertEqual(cfg.qualities, (Quality.Q480, Quality.Q720))
        self.assertEqual(cfg.prefetch, 3)

        # Supervisor
        self.assertEqual(cfg.min_workers, 1)
        self.assertEqual(cfg.max_workers, 6)
        self.assertEqual(cfg.tasks_per_worker, 4)

    def test_load_config_reads_custom_env_values(self) -> None:
        custom_env = {
            "DB_HOST": "postgres",
            "DB_PORT": "5432",
            "DB_NAME": "custom_db",
            "DB_USERNAME": "admin_user",
            "DB_PASSWORD": "secret",
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6380",
            "SERVER_HOST": "127.0.0.1",
            "SERVER_PORT": "9500",
            "MAX_CLIENTS": "25",
            "VIDEOS_DIR": "/tmp/videos",
            "MAX_UPLOAD_MB": "200",
            "SEG_LEN": "6",
            "QUALITIES": "480",
            "PREFETCH": "5",
            "MIN_WORKERS": "2",
            "MAX_WORKERS": "8",
            "TASKS_PER_WORKER": "3",
        }

        cfg = load_config(custom_env)

        self.assertEqual(cfg.db_host, "postgres")
        self.assertEqual(cfg.db_port, 5432)
        self.assertEqual(cfg.db_name, "custom_db")
        self.assertEqual(cfg.db_username, "admin_user")
        self.assertEqual(cfg.db_password, "secret")
        self.assertEqual(
            cfg.db_url,
            "postgresql://admin_user:secret@postgres:5432/custom_db",
        )
        self.assertEqual(cfg.redis_host, "redis")
        self.assertEqual(cfg.redis_port, 6380)
        self.assertEqual(cfg.redis_url, "redis://redis:6380/0")
        self.assertEqual(cfg.server_host, "127.0.0.1")
        self.assertEqual(cfg.server_port, 9500)
        self.assertEqual(cfg.max_clients, 25)
        self.assertEqual(cfg.videos_dir, "/tmp/videos")
        self.assertEqual(cfg.max_upload_mb, 200)
        self.assertEqual(cfg.max_upload_bytes, 200 * 1024 * 1024)
        self.assertEqual(cfg.seg_len, 6)
        self.assertEqual(cfg.qualities, (Quality.Q480,))
        self.assertEqual(cfg.prefetch, 5)
        self.assertEqual(cfg.min_workers, 2)
        self.assertEqual(cfg.max_workers, 8)
        self.assertEqual(cfg.tasks_per_worker, 3)

    def test_load_config_raises_config_error_on_invalid_values(self) -> None:
        invalid_cases = [
            ({"DB_PORT": "no_numerico"}, "DB_PORT"),
            ({"DB_PORT": "0"}, "DB_PORT"),
            ({"DB_PORT": "70000"}, "DB_PORT"),
            ({"REDIS_PORT": "-1"}, "REDIS_PORT"),
            ({"SERVER_PORT": "abc"}, "SERVER_PORT"),
            ({"MAX_CLIENTS": "0"}, "MAX_CLIENTS"),
            ({"MAX_UPLOAD_MB": "0"}, "MAX_UPLOAD_MB"),
            ({"SEG_LEN": "-4"}, "SEG_LEN"),
            ({"PREFETCH": "-1"}, "PREFETCH"),
            ({"QUALITIES": "1080"}, "QUALITIES"),
            ({"QUALITIES": "   "}, "QUALITIES"),
            ({"MIN_WORKERS": "0"}, "MIN_WORKERS"),
            ({"MIN_WORKERS": "5", "MAX_WORKERS": "2"}, "MAX_WORKERS"),
            ({"TASKS_PER_WORKER": "0"}, "TASKS_PER_WORKER"),
        ]

        for bad_env, expected_var in invalid_cases:
            with self.subTest(env=bad_env):
                with self.assertRaises(ConfigError) as ctx:
                    load_config(bad_env)
                self.assertIn(expected_var, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
