"""Servidor TCP multi-hilo para atención concurrente de clientes."""

import socket
from typing import Any, Callable

DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 9000
DEFAULT_BACKLOG: int = 128


class TCPServer:
    """Gestiona el socket de escucha TCP y el ciclo de vida del servidor."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        backlog: int = DEFAULT_BACKLOG,
    ) -> None:
        self.host = host
        self.port = port
        self.backlog = backlog
        self.server_socket: socket.socket | None = None
        self._is_running = False

    def create_server_socket(self) -> socket.socket:
        """Crea el socket TCP con SO_REUSEADDR, realiza el bind y activa listen()."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(self.backlog)
        self.server_socket = sock
        return sock

    def close(self) -> None:
        """Cierra el socket principal de escucha si está abierto."""
        self._is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
