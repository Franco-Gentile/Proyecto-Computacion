"""Excepciones explícitas de la Capa de Dominio."""


class DomainError(Exception):
    """Excepción base para errores de reglas de negocio del dominio."""


class InvalidCredentialsError(DomainError):
    """Credenciales con formato inválido o autenticación fallida."""


class UserAlreadyExistsError(DomainError):
    """Intento de registrar un nombre de usuario que ya existe."""


class VideoNotFoundError(DomainError):
    """El video solicitado no existe en el catálogo."""


class VideoNotReadyError(DomainError):
    """El video existe pero no se encuentra en estado 'ready' para reproducir."""


class InvalidUploadError(DomainError):
    """Parámetros de subida inválidos (extensión, tamaño, título o exceso de bytes)."""


class UploadIncompleteError(DomainError):
    """La subida finalizó con una cantidad de bytes distinta a la declarada."""
