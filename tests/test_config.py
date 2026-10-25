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


if __name__ == "__main__":
    unittest.main()
