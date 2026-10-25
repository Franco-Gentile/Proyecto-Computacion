"""Módulo de configuración de la aplicación (Issue #5)."""

from collections.abc import Mapping
from dataclasses import dataclass
import os

from common.domain.enums import DEFAULT_SEGMENT_DURATION_S, Quality
from common.domain.exceptions import DomainError


class ConfigError(DomainError):
    """Error de configuración ante variables de entorno con valores inválidos."""


def _parse_int(
    source: Mapping[str, str],
    var_name: str,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Lee una variable entera del entorno validando su formato y rango."""
    raw = source.get(var_name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError as exc:
            raise ConfigError(
                f"Variable '{var_name}' inválida: se esperaba un entero y se recibió '{raw}'."
            ) from exc

    if min_value is not None and value < min_value:
        raise ConfigError(
            f"Variable '{var_name}' fuera de rango: {value} debe ser >= {min_value}."
        )
    if max_value is not None and value > max_value:
        raise ConfigError(
            f"Variable '{var_name}' fuera de rango: {value} debe ser <= {max_value}."
        )
    return value


def _parse_qualities(source: Mapping[str, str]) -> tuple[Quality, ...]:
    """Parsea la lista de calidades permitidas desde 'QUALITIES' (ej. '480,720')."""
    if "QUALITIES" not in source:
        return (Quality.Q480, Quality.Q720)

    raw = source["QUALITIES"]
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        raise ConfigError(
            "Variable 'QUALITIES' inválida: debe especificar al menos una calidad (480, 720)."
        )

    parsed: list[Quality] = []
    for part in parts:
        try:
            quality = Quality(int(part))
        except ValueError as exc:
            allowed = ", ".join(str(q.value) for q in Quality)
            raise ConfigError(
                f"Variable 'QUALITIES' inválida: '{part}' no es una calidad soportada ({allowed})."
            ) from exc
        if quality not in parsed:
            parsed.append(quality)

    return tuple(parsed)


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
    db_port = _parse_int(source, "DB_PORT", default=5434, min_value=1, max_value=65535)
    db_name = source.get("DB_NAME", "videoapp_dev").strip() or "videoapp_dev"
    db_username = source.get("DB_USERNAME", "videoapp").strip() or "videoapp"
    db_password = source.get("DB_PASSWORD", "videoapp_dev_pass")
    db_url = (
        source.get("DB_URL", "").strip()
        or f"postgresql://{db_username}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    redis_host = source.get("REDIS_HOST", "localhost").strip() or "localhost"
    redis_port = _parse_int(source, "REDIS_PORT", default=6379, min_value=1, max_value=65535)
    redis_url = (
        source.get("REDIS_URL", "").strip()
        or f"redis://{redis_host}:{redis_port}/0"
    )

    server_host = source.get("SERVER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    server_port = _parse_int(source, "SERVER_PORT", default=9000, min_value=1, max_value=65535)
    max_clients = _parse_int(source, "MAX_CLIENTS", default=50, min_value=1)

    videos_dir = source.get("VIDEOS_DIR", "/data/videos").strip() or "/data/videos"
    max_upload_mb = _parse_int(source, "MAX_UPLOAD_MB", default=500, min_value=1)
    seg_len = _parse_int(
        source,
        "SEG_LEN",
        default=DEFAULT_SEGMENT_DURATION_S,
        min_value=1,
    )
    qualities = _parse_qualities(source)
    prefetch = _parse_int(source, "PREFETCH", default=3, min_value=0)

    min_workers = _parse_int(source, "MIN_WORKERS", default=1, min_value=1)
    max_workers = _parse_int(source, "MAX_WORKERS", default=6, min_value=1)
    if max_workers < min_workers:
        raise ConfigError(
            f"Variable 'MAX_WORKERS' inválida: MAX_WORKERS ({max_workers}) no puede ser menor que MIN_WORKERS ({min_workers})."
        )
    tasks_per_worker = _parse_int(source, "TASKS_PER_WORKER", default=4, min_value=1)

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
