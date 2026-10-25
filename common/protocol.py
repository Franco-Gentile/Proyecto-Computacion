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


class ProtocolError(Exception):
    """Error en el formato, framing o deserialización del protocolo."""


def send_msg(
    sock: socket.socket,
    header: dict[str, Any],
    payload: bytes = b"",
) -> None:
    """Envía un mensaje atómico con framing [4 bytes len][header JSON][payload].

    Garantiza el envío completo mediante `socket.sendall()`.
    """
    if not isinstance(header, dict):
        raise TypeError("El header debe ser un diccionario.")
    if payload is None:
        payload = b""
    elif not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("El payload debe ser de tipo bytes, bytearray o memoryview.")

    header_dict = dict(header)
    header_dict["size"] = len(payload)

    try:
        header_bytes = json.dumps(header_dict, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"No se pudo serializar el header a JSON: {exc}") from exc

    prefix = struct.pack("!I", len(header_bytes))
    sock.sendall(prefix + header_bytes + bytes(payload))


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Lee exactamente `n` bytes del socket.

    Repite lecturas hasta completar los `n` bytes solicitados o lanza `ConnectionError`
    si el socket remoto se cierra antes de completarlos.
    """
    if n < 0:
        raise ValueError("La cantidad de bytes a leer no puede ser negativa.")
    if n == 0:
        return b""

    chunks: list[bytes] = []
    bytes_read = 0

    while bytes_read < n:
        chunk = sock.recv(min(n - bytes_read, 4096))
        if not chunk:
            raise ConnectionError(
                f"Conexión cerrada prematuramente: se esperaban {n} bytes, pero se recibieron {bytes_read}."
            )
        chunks.append(chunk)
        bytes_read += len(chunk)

    return b"".join(chunks)


def recv_msg(sock: socket.socket) -> tuple[dict[str, Any], bytes]:
    """Recibe un mensaje atómico del socket `(header, payload)`.

    Lee el prefijo de 4 bytes con la longitud del header, deserializa el header JSON
    y lee exactamente los bytes del payload según el campo `header["size"]`.
    """
    prefix = _recv_exact(sock, 4)
    header_len = struct.unpack("!I", prefix)[0]

    if header_len > MAX_HEADER_SIZE:
        raise ProtocolError(
            f"El largo del header ({header_len} B) supera el límite permitido ({MAX_HEADER_SIZE} B)."
        )

    header_bytes = _recv_exact(sock, header_len)
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as exc:
        raise ProtocolError(f"Header JSON inválido: {exc}") from exc

    if not isinstance(header, dict):
        raise ProtocolError("El header debe ser un objeto/diccionario JSON.")

    payload_size = header.get("size", 0)
    if not isinstance(payload_size, int) or payload_size < 0:
        raise ProtocolError("El campo 'size' del header debe ser un entero no negativo.")

    payload = _recv_exact(sock, payload_size)
    return header, payload


async def async_send_msg(
    writer: asyncio.StreamWriter,
    header: dict[str, Any],
    payload: bytes = b"",
) -> None:
    """Envía un mensaje de forma asincrónica sobre un StreamWriter con el mismo framing binario."""
    if not isinstance(header, dict):
        raise TypeError("El header debe ser un diccionario.")
    if payload is None:
        payload = b""
    elif not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("El payload debe ser de tipo bytes, bytearray o memoryview.")

    header_dict = dict(header)
    header_dict["size"] = len(payload)

    try:
        header_bytes = json.dumps(header_dict, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"No se pudo serializar el header a JSON: {exc}") from exc

    prefix = struct.pack("!I", len(header_bytes))
    writer.write(prefix + header_bytes + bytes(payload))
    await writer.drain()


async def async_recv_msg(
    reader: asyncio.StreamReader,
) -> tuple[dict[str, Any], bytes]:
    """Recibe un mensaje atómico de forma asincrónica de un StreamReader."""
    try:
        prefix = await reader.readexactly(4)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError(
            f"Conexión cerrada prematuramente: esperados 4 bytes de prefijo, recibidos {len(exc.partial)}."
        ) from exc

    header_len = struct.unpack("!I", prefix)[0]
    if header_len > MAX_HEADER_SIZE:
        raise ProtocolError(
            f"El largo del header ({header_len} B) supera el límite permitido ({MAX_HEADER_SIZE} B)."
        )

    try:
        header_bytes = await reader.readexactly(header_len)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError(
            f"Conexión cerrada prematuramente al leer header: esperados {header_len} bytes, recibidos {len(exc.partial)}."
        ) from exc

    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as exc:
        raise ProtocolError(f"Header JSON inválido: {exc}") from exc

    if not isinstance(header, dict):
        raise ProtocolError("El header debe ser un objeto/diccionario JSON.")

    payload_size = header.get("size", 0)
    if not isinstance(payload_size, int) or payload_size < 0:
        raise ProtocolError("El campo 'size' del header debe ser un entero no negativo.")

    try:
        payload = await reader.readexactly(payload_size)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError(
            f"Conexión cerrada prematuramente al leer payload: esperados {payload_size} bytes, recibidos {len(exc.partial)}."
        ) from exc

    return header, payload
