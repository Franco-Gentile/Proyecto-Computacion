"""Módulo de configuración de la aplicación (Issue #5)."""

from collections.abc import Mapping
from dataclasses import dataclass
import os
import urllib.parse

from common.domain.entities import ScalingConfig
from common.domain.enums import DEFAULT_SEGMENT_DURATION_S, Quality

ALLOWED_DB_SCHEMES: tuple[str, ...] = ("postgresql://", "postgres://")
ALLOWED_REDIS_SCHEMES: tuple[str, ...] = ("redis://", "rediss://")

NUMERIC_INVARIANTS: tuple[tuple[str, int, int | None], ...] = (
    ("db_port", 1, 65535),
    ("redis_port", 1, 65535),
    ("server_port", 1, 65535),
    ("max_clients", 1, None),
    ("max_upload_mb", 1, None),
    ("seg_len", 1, None),
    ("prefetch", 0, None),
    ("min_workers", 1, None),
    ("tasks_per_worker", 1, None),
)


class ConfigError(Exception):
    """Error de configuración ante variables de entorno o invariantes con valores inválidos."""


def _check_in_range(
    name: str,
    value: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> None:
    """Valida que un entero respete los límites inferior y superior definidos."""
    if min_value is not None and value < min_value:
        raise ConfigError(
            f"Variable '{name}' fuera de rango: {value} debe ser >= {min_value}."
        )
    if max_value is not None and value > max_value:
        raise ConfigError(
            f"Variable '{name}' fuera de rango: {value} debe ser <= {max_value}."
        )


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
        return default

    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ConfigError(
            f"Variable '{var_name}' inválida: se esperaba un entero y se recibió '{raw}'."
        ) from exc

    _check_in_range(var_name, value, min_value, max_value)
    return value


def _parse_qualities(source: Mapping[str, str]) -> tuple[Quality, ...]:
    """Parsea la lista de calidades permitidas desde 'QUALITIES' (ej. '480,720')."""
    raw = source.get("QUALITIES")
    if raw is None or not raw.strip():
        return (Quality.Q480, Quality.Q720)

    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        return (Quality.Q480, Quality.Q720)

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


def _validate_db_url(url: str, var_name: str = "DB_URL") -> None:
    """Valida que una URL de base de datos comience con un esquema PostgreSQL permitido."""
    if not any(url.startswith(scheme) for scheme in ALLOWED_DB_SCHEMES):
        allowed = " o ".join(f"'{s}'" for s in ALLOWED_DB_SCHEMES)
        raise ConfigError(
            f"Variable '{var_name}' inválida: debe comenzar con {allowed} y se recibió '{url}'."
        )


def _validate_redis_url(url: str, var_name: str = "REDIS_URL") -> None:
    """Valida que una URL de Redis comience con un esquema Redis permitido."""
    if not any(url.startswith(scheme) for scheme in ALLOWED_REDIS_SCHEMES):
        allowed = " o ".join(f"'{s}'" for s in ALLOWED_REDIS_SCHEMES)
        raise ConfigError(
            f"Variable '{var_name}' inválida: debe comenzar con {allowed} y se recibió '{url}'."
        )


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Configuración inmutable de la aplicación con validación de invariantes."""

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

    def __post_init__(self) -> None:
        """Garantiza las invariantes del objeto independientemente de cómo se instancie."""
        for field_name, min_val, max_val in NUMERIC_INVARIANTS:
            _check_in_range(field_name, getattr(self, field_name), min_val, max_val)

        if self.max_workers < self.min_workers:
            raise ConfigError(
                f"MAX_WORKERS ({self.max_workers}) no puede ser menor que MIN_WORKERS ({self.min_workers})."
            )

        _validate_db_url(self.db_url, "db_url")
        _validate_redis_url(self.redis_url, "redis_url")

    @property
    def max_upload_bytes(self) -> int:
        """Tamaño máximo de subida expresado en bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def scaling(self) -> ScalingConfig:
        """Devuelve la configuración de autoescalado para el supervisor."""
        return ScalingConfig(
            min_workers=self.min_workers,
            max_workers=self.max_workers,
            tasks_per_worker=self.tasks_per_worker,
        )


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Carga la configuración desde variables de entorno con valores por defecto."""
    source = os.environ if env is None else env

    db_host = source.get("DB_HOST", "localhost").strip() or "localhost"
    db_port = _parse_int(source, "DB_PORT", default=5434, min_value=1, max_value=65535)
    db_name = source.get("DB_NAME", "videoapp_dev").strip() or "videoapp_dev"
    db_username = source.get("DB_USERNAME", "videoapp").strip() or "videoapp"
    db_password = source.get("DB_PASSWORD", "videoapp_dev_pass")
    if db_password is not None and not db_password.strip():
        db_password = "videoapp_dev_pass"

    encoded_user = urllib.parse.quote_plus(db_username)
    encoded_pass = urllib.parse.quote_plus(db_password)

    raw_db_url = source.get("DB_URL", "").strip()
    if raw_db_url:
        _validate_db_url(raw_db_url, "DB_URL")
        db_url = raw_db_url
    else:
        db_url = f"postgresql://{encoded_user}:{encoded_pass}@{db_host}:{db_port}/{db_name}"

    redis_host = source.get("REDIS_HOST", "localhost").strip() or "localhost"
    redis_port = _parse_int(source, "REDIS_PORT", default=6379, min_value=1, max_value=65535)

    raw_redis_url = source.get("REDIS_URL", "").strip()
    if raw_redis_url:
        _validate_redis_url(raw_redis_url, "REDIS_URL")
        redis_url = raw_redis_url
    else:
        redis_url = f"redis://{redis_host}:{redis_port}/0"

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

