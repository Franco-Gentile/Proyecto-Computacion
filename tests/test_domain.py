"""Tests unitarios de la Capa de Dominio (common/domain/) aplicando TDD."""

from datetime import datetime, timedelta, timezone
import inspect
import unittest
from uuid import UUID, uuid4

from common.domain import (
    ALLOWED_VIDEO_EXTENSIONS,
    ClusterMetrics,
    DomainError,
    IContainerManager,
    IMediaEngine,
    IPasswordHasher,
    ISegmentCache,
    ITaskQueue,
    IUserRepository,
    IVideoRepository,
    IVideoStorage,
    InvalidCredentialsError,
    InvalidUploadError,
    Quality,
    UploadIncompleteError,
    UploadSession,
    User,
    UserAlreadyExistsError,
    Video,
    VideoNotFoundError,
    VideoNotReadyError,
    VideoSegment,
    VideoStatus,
    calculate_desired_workers,
    calculate_total_segments,
    determine_available_qualities,
    validate_password,
    validate_upload_metadata,
    validate_username,
)


class TestDomainEnumsAndExceptions(unittest.TestCase):
    """Pruebas para enumeraciones y jerarquía de excepciones de dominio."""

    def test_video_status_values(self) -> None:
        self.assertEqual(VideoStatus.UPLOADING.value, "uploading")
        self.assertEqual(VideoStatus.PROCESSING.value, "processing")
        self.assertEqual(VideoStatus.READY.value, "ready")
        self.assertEqual(VideoStatus.ERROR.value, "error")

    def test_quality_values(self) -> None:
        self.assertEqual(Quality.Q480.value, 480)
        self.assertEqual(Quality.Q720.value, 720)

    def test_allowed_extensions(self) -> None:
        self.assertEqual(
            ALLOWED_VIDEO_EXTENSIONS,
            frozenset({"mp4", "mkv", "webm", "mov", "avi"}),
        )

    def test_domain_exceptions_hierarchy(self) -> None:
        exceptions = [
            InvalidCredentialsError,
            UserAlreadyExistsError,
            VideoNotFoundError,
            VideoNotReadyError,
            InvalidUploadError,
            UploadIncompleteError,
        ]
        for exc_cls in exceptions:
            with self.subTest(exception=exc_cls.__name__):
                self.assertTrue(issubclass(exc_cls, DomainError))


class TestDomainPureRules(unittest.TestCase):
    """Pruebas de reglas de negocio puras del dominio."""

    def test_validate_username_accepts_valid_names(self) -> None:
        for valid_name in ("abc", "fran_rodeles", "User_123", "a" * 32):
            with self.subTest(username=valid_name):
                validate_username(valid_name)

    def test_validate_username_rejects_invalid_names(self) -> None:
        invalid_names = ("", "ab", "a" * 33, "con espacio", "user@mail", "usuario-1")
        for invalid_name in invalid_names:
            with self.subTest(username=invalid_name):
                with self.assertRaises(InvalidCredentialsError):
                    validate_username(invalid_name)

    def test_validate_password_accepts_six_or_more_chars(self) -> None:
        validate_password("123456")
        validate_password("clave_segura_2026")

    def test_validate_password_rejects_short_passwords(self) -> None:
        for short_pwd in ("", "123", "12345"):
            with self.subTest(password=short_pwd):
                with self.assertRaises(InvalidCredentialsError):
                    validate_password(short_pwd)

    def test_validate_upload_metadata_valid(self) -> None:
        ext = validate_upload_metadata(
            title="Mi Video",
            filename="clase_01.MP4",
            size_bytes=10 * 1024 * 1024,
            max_upload_bytes=100 * 1024 * 1024,
        )
        self.assertEqual(ext, "mp4")

    def test_validate_upload_metadata_rejects_invalid_cases(self) -> None:
        max_bytes = 50 * 1024 * 1024
        cases = [
            ("", "video.mp4", 1024),
            ("   ", "video.mp4", 1024),
            ("Titulo", "video.exe", 1024),
            ("Titulo", "sin_extension", 1024),
            ("Titulo", "video.mp4", 0),
            ("Titulo", "video.mp4", -10),
            ("Titulo", "video.mp4", max_bytes + 1),
        ]
        for title, filename, size in cases:
            with self.subTest(title=title, filename=filename, size=size):
                with self.assertRaises(InvalidUploadError):
                    validate_upload_metadata(title, filename, size, max_bytes)

    def test_determine_available_qualities_by_height(self) -> None:
        self.assertEqual(determine_available_qualities(360), [Quality.Q480])
        self.assertEqual(determine_available_qualities(480), [Quality.Q480])
        self.assertEqual(
            determine_available_qualities(720),
            [Quality.Q480, Quality.Q720],
        )
        self.assertEqual(
            determine_available_qualities(1080),
            [Quality.Q480, Quality.Q720],
        )
        self.assertEqual(determine_available_qualities(0), [])

    def test_calculate_total_segments(self) -> None:
        self.assertEqual(calculate_total_segments(0.0, seg_len=4), 0)
        self.assertEqual(calculate_total_segments(2.5, seg_len=4), 1)
        self.assertEqual(calculate_total_segments(4.0, seg_len=4), 1)
        self.assertEqual(calculate_total_segments(8.0, seg_len=4), 2)
        self.assertEqual(calculate_total_segments(10.1, seg_len=4), 3)

    def test_calculate_desired_workers_scales_up_fast_and_clamps(self) -> None:
        # Cola vacía -> respeta mínimo
        self.assertEqual(
            calculate_desired_workers(
                pending_tasks=0,
                current_workers=1,
                tasks_per_worker=4,
                min_workers=1,
                max_workers=6,
            ),
            1,
        )
        # Carga media (15 tareas / 4 por worker = ceil(3.75) = 4) -> sube rápido de 1 a 4
        self.assertEqual(
            calculate_desired_workers(
                pending_tasks=15,
                current_workers=1,
                tasks_per_worker=4,
                min_workers=1,
                max_workers=6,
            ),
            4,
        )
        # Carga alta -> limita en max_workers
        self.assertEqual(
            calculate_desired_workers(
                pending_tasks=100,
                current_workers=2,
                tasks_per_worker=4,
                min_workers=1,
                max_workers=6,
            ),
            6,
        )

    def test_calculate_desired_workers_hysteresis_and_cooldown(self) -> None:
        now = datetime(2026, 10, 25, 18, 0, 0, tzinfo=timezone.utc)
        # En ventana de cooldown tras una subida reciente: no baja
        self.assertEqual(
            calculate_desired_workers(
                pending_tasks=0,
                current_workers=4,
                tasks_per_worker=4,
                min_workers=1,
                max_workers=6,
                last_scale_up_at=now - timedelta(seconds=5),
                now=now,
                cooldown_s=15.0,
            ),
            4,
        )
        # Pasado el cooldown: baja gradualmente de a 1 worker por vez (de 4 a 3)
        self.assertEqual(
            calculate_desired_workers(
                pending_tasks=0,
                current_workers=4,
                tasks_per_worker=4,
                min_workers=1,
                max_workers=6,
                last_scale_up_at=now - timedelta(seconds=20),
                now=now,
                cooldown_s=15.0,
            ),
            3,
        )


class TestDomainEntities(unittest.TestCase):
    """Pruebas de las entidades y Value Objects (dataclass)."""

    def test_user_entity_creation(self) -> None:
        user = User(id=1, username="fran_1", password_hash="scrypt$hash")
        self.assertEqual(user.id, 1)
        self.assertEqual(user.username, "fran_1")
        self.assertIsInstance(user.created_at, datetime)

    def test_video_entity_methods(self) -> None:
        vid_id = uuid4()
        video = Video(
            id=vid_id,
            owner_id=1,
            title="Demo Concurrencia",
            original_filename="demo.mp4",
            path=f"/data/videos/{vid_id}.mp4",
            size_bytes=4096,
            duration_s=14.2,
            width=1920,
            height=1080,
            status=VideoStatus.READY,
        )
        self.assertEqual(video.available_qualities(), [Quality.Q480, Quality.Q720])
        self.assertEqual(video.total_segments(seg_len=4), 4)

    def test_video_segment_is_immutable(self) -> None:
        seg = VideoSegment(video_id=uuid4(), quality=Quality.Q480, index=2)
        self.assertEqual(seg.duration_s, 4)
        with self.assertRaises(Exception):
            seg.index = 5  # type: ignore[misc]

    def test_upload_session_tracks_progress_and_overflow(self) -> None:
        session = UploadSession(
            video_id=uuid4(),
            owner_id=1,
            expected_bytes=100,
            temp_path="/data/videos/test.part",
            final_path="/data/videos/test.mp4",
        )
        self.assertFalse(session.is_complete)
        session.record_chunk(60)
        self.assertEqual(session.received_bytes, 60)
        session.record_chunk(40)
        self.assertTrue(session.is_complete)

        with self.assertRaises(InvalidUploadError):
            session.record_chunk(1)

    def test_cluster_metrics_total_pending(self) -> None:
        metrics = ClusterMetrics(
            pending_urgent=3,
            pending_prefetch=9,
            active_workers=2,
            desired_workers=3,
        )
        self.assertEqual(metrics.total_pending, 12)


class TestDomainPortsProtocols(unittest.TestCase):
    """Verifica que las interfaces (typing.Protocol) estén bien definidas."""

    def test_protocols_are_runtime_checkable_and_have_expected_methods(self) -> None:
        expected_ports = {
            IUserRepository: {"create", "get_by_username", "get_by_id"},
            IPasswordHasher: {"hash_password", "verify_password"},
            IVideoRepository: {
                "create",
                "get_by_id",
                "update_status_and_metadata",
                "list_ready",
                "list_by_owner",
                "delete",
            },
            IVideoStorage: {
                "create_temp_file",
                "append_chunk",
                "finalize_upload",
                "remove_files",
            },
            ISegmentCache: {
                "get_segment",
                "put_segment",
                "try_lock_segment",
                "release_lock",
                "notify_segment_ready",
                "notify_segment_error",
                "wait_for_segment",
            },
            ITaskQueue: {"enqueue_probe", "enqueue_transcode"},
            IMediaEngine: {"probe", "transcode_segment"},
            IContainerManager: {
                "get_queue_and_worker_metrics",
                "list_dynamic_workers",
                "spawn_worker",
                "shutdown_and_remove_worker",
                "publish_supervisor_metrics",
                "get_supervisor_metrics",
            },
        }

        for protocol_cls, methods in expected_ports.items():
            with self.subTest(protocol=protocol_cls.__name__):
                self.assertTrue(getattr(protocol_cls, "_is_protocol", False))
                self.assertTrue(getattr(protocol_cls, "_is_runtime_protocol", False))
                members = {
                    name
                    for name, _ in inspect.getmembers(
                        protocol_cls, predicate=inspect.isfunction
                    )
                }
                self.assertTrue(
                    methods.issubset(members),
                    f"Faltan métodos en {protocol_cls.__name__}: {methods - members}",
                )


if __name__ == "__main__":
    unittest.main()
