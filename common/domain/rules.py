"""Reglas de negocio puras del dominio (sin dependencias externas)."""

from datetime import datetime, timezone
import math
from pathlib import PurePath
import re

from common.domain.entities import ScalingConfig
from common.domain.enums import (
    ALLOWED_VIDEO_EXTENSIONS,
    DEFAULT_SEGMENT_DURATION_S,
    Quality,
)
from common.domain.exceptions import InvalidCredentialsError, InvalidUploadError

_USERNAME_PATTERN = re.compile(r"\A[a-zA-Z0-9_]{3,32}\Z")
_MIN_PASSWORD_LENGTH = 6


def validate_username(username: str) -> None:
    """Valida que el username tenga entre 3 y 32 caracteres alfanuméricos o '_'."""
    if not isinstance(username, str) or not _USERNAME_PATTERN.fullmatch(username):
        raise InvalidCredentialsError(
            "El nombre de usuario debe tener entre 3 y 32 caracteres alfanuméricos o '_'."
        )


def validate_password(password: str) -> None:
    """Valida que la contraseña tenga al menos 6 caracteres."""
    if not isinstance(password, str) or len(password) < _MIN_PASSWORD_LENGTH:
        raise InvalidCredentialsError(
            f"La contraseña debe tener al menos {_MIN_PASSWORD_LENGTH} caracteres."
        )


def validate_upload_metadata(
    title: str,
    filename: str,
    size_bytes: int,
    max_upload_bytes: int,
) -> str:
    """Valida título, extensión permitida y tamaño declarado del archivo a subir.

    Devuelve la extensión normalizada en minúsculas (sin punto).
    """
    if not isinstance(title, str) or not title.strip():
        raise InvalidUploadError("El título del video no puede estar vacío.")

    suffix = PurePath(filename or "").suffix.lower().lstrip(".")
    if not suffix or suffix not in ALLOWED_VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
        raise InvalidUploadError(
            f"Extensión '{suffix or '(vacía)'}' no permitida. Permitidas: {allowed}."
        )

    if size_bytes <= 0:
        raise InvalidUploadError("El tamaño del archivo debe ser mayor a 0 bytes.")

    if size_bytes > max_upload_bytes:
        raise InvalidUploadError(
            f"El tamaño declarado ({size_bytes} B) supera el máximo permitido ({max_upload_bytes} B)."
        )

    return suffix


def determine_available_qualities(height: int) -> list[Quality]:
    """Determina las calidades disponibles según la altura del video original.

    480p se ofrece siempre que haya resolución válida (> 0); 720p solo si height >= 720.
    """
    if height <= 0:
        return []
    qualities = [Quality.Q480]
    if height >= Quality.Q720.value:
        qualities.append(Quality.Q720)
    return qualities


def calculate_total_segments(
    duration_s: float,
    seg_len: int = DEFAULT_SEGMENT_DURATION_S,
) -> int:
    """Calcula la cantidad total de segmentos de duración `seg_len` segundos."""
    if seg_len <= 0:
        raise ValueError("La duración del segmento debe ser mayor a 0.")
    if duration_s <= 0:
        return 0
    return math.ceil(duration_s / seg_len)


def calculate_desired_workers(
    pending_tasks: int,
    current_workers: int,
    config: ScalingConfig,
    last_scale_up_at: datetime | None = None,
    now: datetime | None = None,
) -> int:
    """Calcula la cantidad deseada de workers aplicando límites, histéresis y cooldown.

    - Fórmula base: `clamp(ceil(pending / tasks_per_worker), min_workers, max_workers)`.
    - Escalado hacia arriba: inmediato hasta el valor requerido.
    - Escalado hacia abajo: respeta ventana de `cooldown_s` tras la última subida y
      reduce como máximo de a 1 worker por ciclo (histéresis).
    - Asegura que el resultado nunca exceda `config.max_workers` ni sea inferior a `config.min_workers`.
    """
    raw_needed = math.ceil(max(0, pending_tasks) / config.tasks_per_worker)
    target = max(config.min_workers, min(config.max_workers, raw_needed))

    if target >= current_workers:
        return target

    if last_scale_up_at is not None and config.cooldown_s > 0:
        reference_now = now or datetime.now(timezone.utc)
        elapsed_s = (reference_now - last_scale_up_at).total_seconds()
        if elapsed_s < config.cooldown_s:
            return min(config.max_workers, max(config.min_workers, current_workers))

    step_down = current_workers - 1
    return min(config.max_workers, max(target, step_down))
