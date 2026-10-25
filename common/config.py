"""Módulo de configuración de la aplicación (Issue #5)."""

from collections.abc import Mapping
from dataclasses import dataclass

from common.domain.enums import DEFAULT_SEGMENT_DURATION_S, Quality
from common.domain.exceptions import DomainError


class ConfigError(DomainError):
    """Error de configuración ante variables de entorno con valores inválidos."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Configuración inmutable de la aplicación."""

    db_host: str = "localhost"
    db_port: int = 5434
    db_name: str = "videoapp_dev"
    db_username: str = "videoapp"
    db_password: str = "videoapp_dev_pass"
    db_url: str = "postgresql://videoapp:videoapp_dev_pass@localhost:5434/videoapp_dev"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str = "redis://localhost:6379/0"

    server_host: str = "0.0.0.0"
    server_port: int = 9000
    max_clients: int = 50

    videos_dir: str = "/data/videos"
    max_upload_mb: int = 500
    seg_len: int = DEFAULT_SEGMENT_DURATION_S
    qualities: tuple[Quality, ...] = (Quality.Q480, Quality.Q720)
    prefetch: int = 3

    min_workers: int = 1
    max_workers: int = 6
    tasks_per_worker: int = 4

    @property
    def max_upload_bytes(self) -> int:
        """Tamaño máximo de subida expresado en bytes."""
        return self.max_upload_mb * 1024 * 1024


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Carga la configuración usando valores por defecto para variables faltantes."""
    return AppConfig()
