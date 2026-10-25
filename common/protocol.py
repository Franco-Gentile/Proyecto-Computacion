"""Protocolo de mensajería sincrónico y asincrónico para comunicación cliente-servidor.

Estructura de la trama:
[4 bytes largo header en big-endian (unsigned int)]
[header codificado en JSON UTF-8 (contiene clave "size" con el largo del payload)]
[payload binario de header["size"] bytes]
"""

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
