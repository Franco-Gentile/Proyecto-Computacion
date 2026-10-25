"""Módulo de configuración de la aplicación (Issue #5)."""

from collections.abc import Mapping
from dataclasses import dataclass
import os

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
    """Carga la configuración desde variables de entorno con valores por defecto."""
    source = os.environ if env is None else env

    db_host = source.get("DB_HOST", "localhost").strip() or "localhost"
    db_port = int(source.get("DB_PORT", "5434"))
    db_name = source.get("DB_NAME", "videoapp_dev").strip() or "videoapp_dev"
    db_username = source.get("DB_USERNAME", "videoapp").strip() or "videoapp"
    db_password = source.get("DB_PASSWORD", "videoapp_dev_pass")
    db_url = (
        source.get("DB_URL", "").strip()
        or f"postgresql://{db_username}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    redis_host = source.get("REDIS_HOST", "localhost").strip() or "localhost"
    redis_port = int(source.get("REDIS_PORT", "6379"))
    redis_url = (
        source.get("REDIS_URL", "").strip()
        or f"redis://{redis_host}:{redis_port}/0"
    )

    server_host = source.get("SERVER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    server_port = int(source.get("SERVER_PORT", "9000"))
    max_clients = int(source.get("MAX_CLIENTS", "50"))

    videos_dir = source.get("VIDEOS_DIR", "/data/videos").strip() or "/data/videos"
    max_upload_mb = int(source.get("MAX_UPLOAD_MB", "500"))
    seg_len = int(source.get("SEG_LEN", str(DEFAULT_SEGMENT_DURATION_S)))

    raw_qualities = source.get("QUALITIES", "480,720")
    qualities = tuple(
        Quality(int(part.strip()))
        for part in raw_qualities.split(",")
        if part.strip()
    )

    prefetch = int(source.get("PREFETCH", "3"))
    min_workers = int(source.get("MIN_WORKERS", "1"))
    max_workers = int(source.get("MAX_WORKERS", "6"))
    tasks_per_worker = int(source.get("TASKS_PER_WORKER", "4"))

    return AppConfig(
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_username=db_username,
        db_password=db_password,
        db_url=db_url,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_url=redis_url,
        server_host=server_host,
        server_port=server_port,
        max_clients=max_clients,
        videos_dir=videos_dir,
        max_upload_mb=max_upload_mb,
        seg_len=seg_len,
        qualities=qualities,
        prefetch=prefetch,
        min_workers=min_workers,
        max_workers=max_workers,
        tasks_per_worker=tasks_per_worker,
    )
