"""Servidor TCP multi-hilo para atención concurrente de clientes."""

import logging
import socket
import threading
from typing import Any, Callable

from server.handler import ClientHandler

logger = logging.getLogger(__name__)

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
        handler_factory: Callable[[socket.socket, tuple[str, int]], Any] = ClientHandler,
    ) -> None:
        self.host = host
        self.port = port
        self.backlog = backlog
        self.handler_factory = handler_factory
        self.server_socket: socket.socket | None = None
        self._is_running = False
        self._listener_thread: threading.Thread | None = None
        self._client_threads: list[threading.Thread] = []
        self._client_sockets: set[socket.socket] = set()
        self._lock = threading.Lock()

    def create_server_socket(self) -> socket.socket:
        """Crea el socket TCP con SO_REUSEADDR, realiza el bind y activa listen()."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(self.backlog)
        sock.settimeout(0.5)
        self.server_socket = sock
        return sock

    def start(self) -> None:
        """Inicia el socket y el hilo de aceptación en segundo plano."""
        if self._is_running:
            return
        if self.server_socket is None:
            self.create_server_socket()
        self._is_running = True
        self._listener_thread = threading.Thread(
            target=self._accept_loop,
            name="TCPServer-Listener",
            daemon=True,
        )
        self._listener_thread.start()

    def _run_client(self, handler: Any, client_sock: socket.socket) -> None:
        """Ejecuta el handler del cliente y garantiza la limpieza del socket y registro."""
        try:
            handler.handle_client()
        finally:
            try:
                client_sock.close()
            except OSError:
                pass
            current = threading.current_thread()
            with self._lock:
                self._client_sockets.discard(client_sock)
                self._client_threads = [
                    t for t in self._client_threads if t is not current and t.is_alive()
                ]

    def _accept_loop(self) -> None:
        """Loop que acepta conexiones entrantes y despacha cada cliente a un nuevo hilo."""
        while self._is_running and self.server_socket:
            try:
                client_sock, client_addr = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            if not self._is_running:
                try:
                    client_sock.close()
                except OSError:
                    pass
                break

            try:
                handler = self.handler_factory(client_sock, client_addr)
                thread = threading.Thread(
                    target=self._run_client,
                    args=(handler, client_sock),
                    name=f"ClientThread-{client_addr[0]}:{client_addr[1]}",
                    daemon=True,
                )
                with self._lock:
                    self._client_threads = [t for t in self._client_threads if t.is_alive()]
                    self._client_threads.append(thread)
                    self._client_sockets.add(client_sock)
                thread.start()
            except Exception as exc:
                logger.exception("Error al inicializar cliente %s: %s", client_addr, exc)
                with self._lock:
                    self._client_sockets.discard(client_sock)
                    self._client_threads = [t for t in self._client_threads if t.is_alive()]
                try:
                    client_sock.close()
                except OSError:
                    pass

    def stop(self) -> None:
        """Detiene la aceptación de conexiones y cierra los sockets activos."""
        self._is_running = False
        self.close()
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2.0)

        with self._lock:
            active_sockets = list(self._client_sockets)
            active_threads = list(self._client_threads)
            self._client_sockets.clear()
            self._client_threads.clear()

        for sock in active_sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

        for thread in active_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)

    def close(self) -> None:
        """Cierra el socket principal de escucha si está abierto."""
        self._is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
