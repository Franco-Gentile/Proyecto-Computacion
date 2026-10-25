"""Enumeraciones y constantes del dominio."""

from enum import Enum


class VideoStatus(str, Enum):
    """Estados posibles del ciclo de vida de un video."""

    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Quality(int, Enum):
    """Calidades de transcodificación soportadas (altura en píxeles)."""

    Q480 = 480
    Q720 = 720


ALLOWED_VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {"mp4", "mkv", "webm", "mov", "avi"}
)
