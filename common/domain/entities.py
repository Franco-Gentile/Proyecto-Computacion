"""Entidades y Value Objects de la Capa de Dominio."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from uuid import UUID

from common.domain.enums import (
    DEFAULT_SEGMENT_DURATION_S,
    Quality,
    VideoStatus,
)
from common.domain.exceptions import InvalidUploadError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class User:
    """Entidad de usuario registrado en el sistema."""

    id: int | None
    username: str
    password_hash: str
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class Video:
    """Entidad que representa un video y sus metadatos técnicos."""

    id: UUID
    owner_id: int
    title: str
    original_filename: str
    path: str
    size_bytes: int
    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    status: VideoStatus = VideoStatus.UPLOADING
    created_at: datetime = field(default_factory=_utc_now)

    def available_qualities(self) -> list[Quality]:
        """Devuelve las calidades disponibles según la altura del video."""
        if self.height <= 0:
            return []
        qualities = [Quality.Q480]
        if self.height >= Quality.Q720.value:
            qualities.append(Quality.Q720)
        return qualities

    def total_segments(self, seg_len: int = DEFAULT_SEGMENT_DURATION_S) -> int:
        """Devuelve el número total de segmentos para la duración del video."""
        if seg_len <= 0:
            raise ValueError("La duración del segmento debe ser mayor a 0.")
        if self.duration_s <= 0:
            return 0
        return math.ceil(self.duration_s / seg_len)


@dataclass(frozen=True, slots=True)
class VideoSegment:
    """Value Object inmutable que identifica un segmento de video a procesar/transmitir."""

    video_id: UUID
    quality: Quality
    index: int
    duration_s: int = DEFAULT_SEGMENT_DURATION_S


@dataclass(slots=True)
class UploadSession:
    """Estado de una sesión de subida de archivo por bloques (chunks)."""

    video_id: UUID
    owner_id: int
    expected_bytes: int
    temp_path: str
    final_path: str
    received_bytes: int = 0

    @property
    def is_complete(self) -> bool:
        """Indica si los bytes recibidos coinciden exactamente con los esperados."""
        return self.received_bytes == self.expected_bytes

    def record_chunk(self, chunk_size: int) -> None:
        """Acumula el tamaño de un bloque recibido validando que no supere el total declarado."""
        if chunk_size < 0:
            raise InvalidUploadError("El tamaño del chunk no puede ser negativo.")
        if self.received_bytes + chunk_size > self.expected_bytes:
            raise InvalidUploadError(
                f"Bytes recibidos ({self.received_bytes + chunk_size}) superan "
                f"el tamaño declarado ({self.expected_bytes})."
            )
        self.received_bytes += chunk_size


@dataclass(slots=True)
class ClusterMetrics:
    """Fotografía de métricas de carga y workers para el supervisor."""

    pending_urgent: int
    pending_prefetch: int
    active_workers: int
    desired_workers: int
    last_scale_up_at: datetime | None = None

    @property
    def total_pending(self) -> int:
        """Total de tareas pendientes sumando las colas urgent y prefetch."""
        return self.pending_urgent + self.pending_prefetch


@dataclass(frozen=True, slots=True)
class ScalingConfig:
    """Configuración inmutable de las políticas de autoescalado de workers."""

    min_workers: int = 1
    max_workers: int = 6
    tasks_per_worker: int = 4
    cooldown_s: float = 15.0

    def __post_init__(self) -> None:
        if self.tasks_per_worker <= 0:
            raise ValueError("tasks_per_worker debe ser mayor a 0.")
        if self.min_workers < 1 or self.max_workers < self.min_workers:
            raise ValueError("Rango inválido para min_workers y max_workers.")
        if self.cooldown_s < 0:
            raise ValueError("cooldown_s no puede ser negativo.")
