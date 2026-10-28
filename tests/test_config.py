"""Tests unitarios para el módulo de configuración (common/config.py - Issue #5)."""

from pathlib import Path
import unittest

from common.config import AppConfig, ConfigError, load_config
from common.domain.entities import ScalingConfig
from common.domain.enums import Quality
from common.domain.exceptions import DomainError

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestLoadConfigDefaults(unittest.TestCase):
    """Ciclo 1 TDD: una variable faltante usa su valor por defecto de dev."""

    def test_config_error_does_not_inherit_from_domain_error(self) -> None:
        """ConfigError representa error de arranque/infra, no una regla de negocio del dominio."""
        self.assertTrue(issubclass(ConfigError, Exception))
        self.assertFalse(issubclass(ConfigError, DomainError))

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

        # Supervisor y ScalingConfig
        self.assertEqual(cfg.min_workers, 1)
        self.assertEqual(cfg.max_workers, 6)
        self.assertEqual(cfg.tasks_per_worker, 4)
        self.assertIsInstance(cfg.scaling, ScalingConfig)
        self.assertEqual(cfg.scaling.min_workers, 1)
        self.assertEqual(cfg.scaling.max_workers, 6)
        self.assertEqual(cfg.scaling.tasks_per_worker, 4)

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
        self.assertEqual(cfg.scaling.min_workers, 2)
        self.assertEqual(cfg.scaling.max_workers, 8)

    def test_granular_db_and_redis_vars_drive_urls_when_url_omitted(self) -> None:
        """Si DB_URL o REDIS_URL no están definidos, se construyen con las variables granulares."""
        env = {
            "DB_HOST": "postgres_custom",
            "DB_PORT": "5433",
            "REDIS_HOST": "redis_custom",
            "REDIS_PORT": "6381",
        }
        cfg = load_config(env)
        self.assertIn("@postgres_custom:5433/", cfg.db_url)
        self.assertEqual(cfg.redis_url, "redis://redis_custom:6381/0")

    def test_explicit_valid_url_overrides_granular_vars(self) -> None:
        """Si se pasa DB_URL o REDIS_URL explícita y válida, toma precedencia."""
        env = {
            "DB_HOST": "ignored_host",
            "DB_URL": "postgresql://custom_override:pass@remote:5432/override_db",
            "REDIS_URL": "redis://remote_redis:6379/1",
        }
        cfg = load_config(env)
        self.assertEqual(cfg.db_url, "postgresql://custom_override:pass@remote:5432/override_db")
        self.assertEqual(cfg.redis_url, "redis://remote_redis:6379/1")

    def test_special_characters_in_credentials_are_url_encoded(self) -> None:
        """Caracteres especiales en usuario o password (@, :, /, #, %) se escapan con quote_plus."""
        env = {
            "DB_USERNAME": "user@domain:test",
            "DB_PASSWORD": "p@ss:w/ord#1%2",
        }
        cfg = load_config(env)
        self.assertIn("user%40domain%3Atest", cfg.db_url)
        self.assertIn("p%40ss%3Aw%2Ford%231%252", cfg.db_url)

    def test_blank_and_whitespace_values_fall_back_consistently_to_defaults(self) -> None:
        """Variables pasadas como strings vacíos o solo espacios toman el valor por defecto."""
        env = {
            "DB_PORT": "   ",
            "REDIS_PORT": "",
            "DB_PASSWORD": "   ",
            "QUALITIES": "   ",
            "DB_URL": "   ",
            "REDIS_URL": "",
        }
        cfg = load_config(env)
        self.assertEqual(cfg.db_port, 5434)
        self.assertEqual(cfg.redis_port, 6379)
        self.assertEqual(cfg.db_password, "videoapp_dev_pass")
        self.assertEqual(cfg.qualities, (Quality.Q480, Quality.Q720))
        self.assertEqual(
            cfg.db_url,
            "postgresql://videoapp:videoapp_dev_pass@localhost:5434/videoapp_dev",
        )
        self.assertEqual(cfg.redis_url, "redis://localhost:6379/0")

    def test_invalid_url_scheme_raises_config_error(self) -> None:
        """URLs con esquema no permitido (ej. http://) deben fallar con ConfigError."""
        with self.assertRaises(ConfigError) as ctx_db:
            load_config({"DB_URL": "http://localhost:5432/db"})
        self.assertIn("DB_URL", str(ctx_db.exception))

        with self.assertRaises(ConfigError) as ctx_redis:
            load_config({"REDIS_URL": "http://localhost:6379/0"})
        self.assertIn("REDIS_URL", str(ctx_redis.exception))

    def test_app_config_direct_instantiation_validates_invariants(self) -> None:
        """Instanciar AppConfig directamente valida invariantes en __post_init__."""
        invalid_invariants = [
            {"min_workers": 8, "max_workers": 2},
            {"db_port": 0},
            {"db_port": 70000},
            {"redis_port": -1},
            {"server_port": 0},
            {"max_clients": 0},
            {"max_upload_mb": 0},
            {"seg_len": 0},
            {"tasks_per_worker": 0},
            {"db_url": "mysql://user:pass@localhost/db"},
            {"redis_url": "memcached://localhost"},
        ]
        for kwargs in invalid_invariants:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ConfigError):
                    AppConfig(**kwargs)

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
            ({"MIN_WORKERS": "0"}, "MIN_WORKERS"),
            ({"MIN_WORKERS": "5", "MAX_WORKERS": "2"}, "MAX_WORKERS"),
            ({"TASKS_PER_WORKER": "0"}, "TASKS_PER_WORKER"),
        ]

        for bad_env, expected_var in invalid_cases:
            with self.subTest(env=bad_env):
                with self.assertRaises(ConfigError) as ctx:
                    load_config(bad_env)
                self.assertIn(expected_var, str(ctx.exception))

    def test_env_example_file_exists_and_loads_valid_config(self) -> None:
        env_example_path = ROOT_DIR / ".env.example"
        self.assertTrue(
            env_example_path.is_file(),
            "El archivo .env.example no existe en la raíz del repositorio.",
        )

        parsed_env: dict[str, str] = {}
        for line in env_example_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, _, value = stripped.partition("=")
            parsed_env[key.strip()] = value.strip()

        required_keys = {
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USERNAME",
            "DB_PASSWORD",
            "REDIS_HOST",
            "REDIS_PORT",
            "SERVER_HOST",
            "SERVER_PORT",
            "MAX_CLIENTS",
            "VIDEOS_DIR",
            "MAX_UPLOAD_MB",
            "SEG_LEN",
            "QUALITIES",
            "PREFETCH",
            "MIN_WORKERS",
            "MAX_WORKERS",
            "TASKS_PER_WORKER",
        }
        self.assertTrue(
            required_keys.issubset(parsed_env.keys()),
            f"Faltan variables en .env.example: {required_keys - parsed_env.keys()}",
        )

        cfg = load_config(parsed_env)
        self.assertEqual(cfg.db_port, 5434)
        self.assertEqual(cfg.db_name, "videoapp_dev")


if __name__ == "__main__":
    unittest.main()

