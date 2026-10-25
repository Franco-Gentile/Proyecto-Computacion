"""Capa de Dominio: Entidades, enumeraciones, reglas de negocio puras y contratos (Protocol)."""

from common.domain.entities import (
    ClusterMetrics,
    ScalingConfig,
    UploadSession,
    User,
    Video,
    VideoSegment,
)
from common.domain.enums import (
    ALLOWED_VIDEO_EXTENSIONS,
    DEFAULT_SEGMENT_DURATION_S,
    Quality,
    VideoStatus,
)
from common.domain.exceptions import (
    DomainError,
    InvalidCredentialsError,
    InvalidUploadError,
    UploadIncompleteError,
    UserAlreadyExistsError,
    VideoNotFoundError,
    VideoNotReadyError,
)
from common.domain.ports import (
    IContainerManager,
    IMediaEngine,
    IPasswordHasher,
    ISegmentCache,
    ITaskQueue,
    IUserRepository,
    IVideoRepository,
    IVideoStorage,
)
from common.domain.rules import (
    calculate_desired_workers,
    calculate_total_segments,
    determine_available_qualities,
    validate_password,
    validate_upload_metadata,
    validate_username,
)

__all__ = [
    "ALLOWED_VIDEO_EXTENSIONS",
    "ClusterMetrics",
    "DEFAULT_SEGMENT_DURATION_S",
    "DomainError",
    "IContainerManager",
    "IMediaEngine",
    "IPasswordHasher",
    "ISegmentCache",
    "ITaskQueue",
    "IUserRepository",
    "IVideoRepository",
    "IVideoStorage",
    "InvalidCredentialsError",
    "InvalidUploadError",
    "Quality",
    "ScalingConfig",
    "UploadIncompleteError",
    "UploadSession",
    "User",
    "UserAlreadyExistsError",
    "Video",
    "VideoNotFoundError",
    "VideoNotReadyError",
    "VideoSegment",
    "VideoStatus",
    "calculate_desired_workers",
    "calculate_total_segments",
    "determine_available_qualities",
    "validate_password",
    "validate_upload_metadata",
    "validate_username",
]
