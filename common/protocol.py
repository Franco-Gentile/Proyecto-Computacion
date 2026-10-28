"""Protocolo de mensajería sincrónico y asincrónico para comunicación cliente-servidor.

Estructura de la trama:
[4 bytes largo header en big-endian (unsigned int)]
[header codificado en JSON UTF-8 (contiene clave "size" con el largo del payload)]
[payload binario de header["size"] bytes]
"""

import asyncio
import json
import socket
import struct
from typing import Any

MAX_HEADER_SIZE: int = 65536
MAX_PAYLOAD_SIZE: int = 64 * 1024 * 1024
RECV_BUFFER_SIZE: int = 65536


class ProtocolError(Exception):
    """Error en el formato, framing o deserialización del protocolo."""


def _encode_frame(header: dict[str, Any], payload: bytes = b"") -> bytes:
    """Construye los bytes completos de una trama `[4B len][header JSON][payload]`."""
    if not isinstance(header, dict):
        raise TypeError("El header debe ser un diccionario.")
    if payload is None:
        payload = b""
    elif not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("El payload debe ser de tipo bytes, bytearray o memoryview.")

    payload_len = len(payload)
    if payload_len > MAX_PAYLOAD_SIZE:
        raise ProtocolError(
            f"El payload ({payload_len} B) supera el límite de {MAX_PAYLOAD_SIZE} B."
        )

    header_dict = dict(header)
    header_dict["size"] = payload_len

    try:
        header_bytes = json.dumps(header_dict, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"No se pudo serializar el header a JSON: {exc}") from exc

    if len(header_bytes) > MAX_HEADER_SIZE:
        raise ProtocolError(
            f"El header ({len(header_bytes)} B) supera el límite de {MAX_HEADER_SIZE} B."
        )

    prefix = struct.pack("!I", len(header_bytes))
    return prefix + header_bytes + bytes(payload)


def _unpack_and_validate_header_len(prefix: bytes) -> int:
    """Desempaqueta el prefijo de 4 bytes y verifica que no supere MAX_HEADER_SIZE."""
    header_len = struct.unpack("!I", prefix)[0]
    if header_len > MAX_HEADER_SIZE:
        raise ProtocolError(
            f"El largo del header ({header_len} B) supera el límite permitido ({MAX_HEADER_SIZE} B)."
        )
    return header_len


def _decode_and_validate_header(header_bytes: bytes) -> tuple[dict[str, Any], int]:
    """Deserializa el JSON del header y valida su estructura y el campo 'size'."""
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as exc:
        raise ProtocolError(f"Header JSON inválido: {exc}") from exc

    if not isinstance(header, dict):
        raise ProtocolError("El header debe ser un objeto/diccionario JSON.")

    payload_size = header.get("size", 0)
    if (
        isinstance(payload_size, bool)
        or not isinstance(payload_size, int)
        or payload_size < 0
    ):
        raise ProtocolError("El campo 'size' del header debe ser un entero no negativo.")

    if payload_size > MAX_PAYLOAD_SIZE:
        raise ProtocolError(
            f"El tamaño del payload ({payload_size} B) supera el límite permitido ({MAX_PAYLOAD_SIZE} B)."
        )

    return header, payload_size


def send_msg(
    sock: socket.socket,
    header: dict[str, Any],
    payload: bytes = b"",
) -> None:
    """Envía un mensaje atómico con framing [4 bytes len][header JSON][payload].

    Garantiza el envío completo mediante `socket.sendall()`.
    """
    frame = _encode_frame(header, payload)
    sock.sendall(frame)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Lee exactamente `n` bytes del socket sin copias intermedias.

    Lanza `EOFError` si el socket se cierra limpiamente antes de leer el primer byte
    (`bytes_read == 0`), o `ConnectionError` si se interrumpe a mitad de lectura.
    """
    if n < 0:
        raise ValueError("La cantidad de bytes a leer no puede ser negativa.")
    if n == 0:
        return b""

    buf = bytearray(n)
    view = memoryview(buf)
    bytes_read = 0

    while bytes_read < n:
        nbytes = sock.recv_into(view[bytes_read:], min(n - bytes_read, RECV_BUFFER_SIZE))
        if nbytes == 0:
            if bytes_read == 0:
                raise EOFError("Conexión cerrada de forma limpia por el par remoto (EOF).")
            raise ConnectionError(
                f"Conexión cerrada prematuramente: esperados {n} bytes, recibidos {bytes_read}."
            )
        bytes_read += nbytes

    return bytes(buf)


def recv_msg(sock: socket.socket) -> tuple[dict[str, Any], bytes]:
    """Recibe un mensaje atómico del socket `(header, payload)`."""
    prefix = _recv_exact(sock, 4)
    header_len = _unpack_and_validate_header_len(prefix)
    try:
        header_bytes = _recv_exact(sock, header_len)
        header, payload_size = _decode_and_validate_header(header_bytes)
        payload = _recv_exact(sock, payload_size)
    except EOFError as exc:
        raise ConnectionError(
            "Conexión cerrada prematuramente a mitad de trama."
        ) from exc
    return header, payload


async def async_send_msg(
    writer: asyncio.StreamWriter,
    header: dict[str, Any],
    payload: bytes = b"",
) -> None:
    """Envía un mensaje de forma asincrónica sobre un StreamWriter con el mismo framing binario."""
    frame = _encode_frame(header, payload)
    writer.write(frame)
    await writer.drain()


async def async_recv_msg(
    reader: asyncio.StreamReader,
) -> tuple[dict[str, Any], bytes]:
    """Recibe un mensaje atómico de forma asincrónica de un StreamReader."""
    try:
        prefix = await reader.readexactly(4)
    except asyncio.IncompleteReadError as exc:
        if len(exc.partial) == 0:
            raise EOFError("Conexión cerrada de forma limpia por el par remoto (EOF).") from exc
        raise ConnectionError(
            f"Conexión cerrada prematuramente: esperados 4 bytes de prefijo, recibidos {len(exc.partial)}."
        ) from exc

    header_len = _unpack_and_validate_header_len(prefix)

    try:
        header_bytes = await reader.readexactly(header_len)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError(
            f"Conexión cerrada prematuramente al leer header: esperados {header_len} bytes, recibidos {len(exc.partial)}."
        ) from exc

    header, payload_size = _decode_and_validate_header(header_bytes)

    try:
        payload = await reader.readexactly(payload_size)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError(
            f"Conexión cerrada prematuramente al leer payload: esperados {payload_size} bytes, recibidos {len(exc.partial)}."
        ) from exc

    return header, payload
