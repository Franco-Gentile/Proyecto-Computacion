"""Interfaces / Puertos de la Capa de Dominio (Principio de Inversión de Dependencias)."""

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from common.domain.entities import ClusterMetrics, User, Video, VideoSegment
from common.domain.enums import VideoStatus


@runtime_checkable
class IUserRepository(Protocol):
    """Contrato para la persistencia y consulta de usuarios."""

    def create(self, username: str, password_hash: str) -> User:
        """Registra un nuevo usuario o lanza UserAlreadyExistsError si ya existe."""
        ...

    def get_by_username(self, username: str) -> User | None:
        """Busca un usuario por su nombre único."""
        ...

    def get_by_id(self, user_id: int) -> User | None:
        """Busca un usuario por su identificador primario."""
        ...


@runtime_checkable
class IPasswordHasher(Protocol):
    """Contrato para el hasheo y verificación segura de contraseñas."""

    def hash_password(self, raw_password: str) -> str:
        """Genera un hash seguro con salt aleatorio a partir de la contraseña en texto plano."""
        ...

    def verify_password(self, raw_password: str, password_hash: str) -> bool:
        """Verifica en tiempo constante si la contraseña coincide con el hash."""
        ...


@runtime_checkable
class IVideoRepository(Protocol):
    """Contrato para la persistencia y consulta de metadatos de videos."""

    def create(self, video: Video) -> UUID:
        """Inserta un nuevo registro de video y devuelve su UUID."""
        ...

    def get_by_id(self, video_id: UUID) -> Video | None:
        """Obtiene un video por su UUID o None si no existe."""
        ...

    def update_status_and_metadata(
        self,
        video_id: UUID,
        status: VideoStatus,
        duration_s: float = 0.0,
        width: int = 0,
        height: int = 0,
    ) -> None:
        """Actualiza el estado del video y sus dimensiones/duración tras el análisis."""
        ...

    def list_ready(self) -> list[Video]:
        """Devuelve el catálogo público de videos en estado READY ordenados por fecha descendente."""
        ...

    def list_by_owner(self, owner_id: int) -> list[Video]:
        """Lista todos los videos de un usuario en cualquier estado."""
        ...

    def delete(self, video_id: UUID) -> None:
        """Elimina el registro de un video (usado en limpieza de subidas fallidas)."""
        ...


@runtime_checkable
class IVideoStorage(Protocol):
    """Contrato para el almacenamiento de archivos de video en el sistema de archivos."""

    def create_temp_file(self, video_id: UUID) -> str:
        """Crea el archivo temporal (.part) para la subida y devuelve su ruta."""
        ...

    def append_chunk(self, temp_path: str, chunk: bytes) -> None:
        """Escribe un bloque binario al final del archivo temporal."""
        ...

    def finalize_upload(self, video_id: UUID, ext: str) -> str:
        """Promueve el archivo .part a la ruta definitiva `/data/videos/<uuid>.<ext>`."""
        ...

    def remove_files(self, video_id: UUID) -> None:
        """Elimina archivos temporales o finales asociados al UUID dado."""
        ...


@runtime_checkable
class ISegmentCache(Protocol):
    """Contrato para la caché de segmentos, locks de deduplicación y notificación en Redis."""

    def get_segment(self, segment: VideoSegment) -> bytes | None:
        """Obtiene los bytes MPEG-TS de un segmento cacheado o None si no está."""
        ...

    def put_segment(self, segment: VideoSegment, data: bytes) -> None:
        """Almacena los bytes MPEG-TS del segmento en caché con TTL."""
        ...

    def try_lock_segment(self, segment: VideoSegment) -> bool:
        """Intenta adquirir el lock atómico (SET NX EX) para transcodificar el segmento."""
        ...

    def release_lock(self, segment: VideoSegment) -> None:
        """Libera el lock del segmento."""
        ...

    def notify_segment_ready(self, segment: VideoSegment) -> None:
        """Despierta a los hilos en espera notificando que el segmento ya está en caché."""
        ...

    def notify_segment_error(self, segment: VideoSegment) -> None:
        """Publica un marcador de error para desbloquear a los hilos que esperan el segmento."""
        ...

    def wait_for_segment(self, segment: VideoSegment, timeout: int) -> bytes:
        """Espera de forma bloqueante (BLPOP) hasta que el segmento esté listo y lo retorna."""
        ...


@runtime_checkable
class ITaskQueue(Protocol):
    """Contrato para el encolado de tareas asincrónicas hacia los workers."""

    def enqueue_probe(self, video_id: UUID) -> None:
        """Encola la tarea de análisis de metadatos (ffprobe) para un video recién subido."""
        ...

    def enqueue_transcode(self, segment: VideoSegment, priority_queue: str) -> None:
        """Encola la transcodificación de un segmento en la cola indicada ('urgent' o 'prefetch')."""
        ...


@runtime_checkable
class IMediaEngine(Protocol):
    """Contrato para las herramientas de análisis y transcodificación multimedia (ffprobe/ffmpeg)."""

    def probe(self, path: str) -> dict[str, Any]:
        """Extrae duración, ancho, alto e información de streams del archivo de video."""
        ...

    def transcode_segment(self, path: str, segment: VideoSegment) -> bytes:
        """Transcodifica el segmento a MPEG-TS en la calidad solicitada y retorna sus bytes."""
        ...


@runtime_checkable
class IContainerManager(Protocol):
    """Contrato para la lectura de carga del cluster y gestión de contenedores worker dinámicos."""

    def get_queue_and_worker_metrics(self) -> ClusterMetrics:
        """Lee la longitud de las colas y los heartbeats activos para construir las métricas."""
        ...

    def list_dynamic_workers(self) -> list[str]:
        """Lista los nombres de los contenedores dinámicos (`videoapp.role=worker-dyn`)."""
        ...

    def spawn_worker(self) -> str:
        """Crea e inicia un nuevo contenedor worker dinámico y devuelve su nombre."""
        ...

    def shutdown_and_remove_worker(self, worker_name: str) -> None:
        """Solicita apagado ordenado al worker Celery y elimina su contenedor."""
        ...

    def publish_supervisor_metrics(self, metrics: ClusterMetrics) -> None:
        """Publica el estado actual del supervisor en Redis para el comando STATUS."""
        ...

    def get_supervisor_metrics(self) -> ClusterMetrics | None:
        """Obtiene las últimas métricas publicadas por el supervisor."""
        ...
