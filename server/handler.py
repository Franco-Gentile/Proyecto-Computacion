"""Manejador de sesión de cliente TCP y despacho dinámico de comandos."""

import logging
import socket
from typing import Any

from common.domain.entities import UploadSession, User
from common.protocol import ProtocolError, recv_msg, send_msg

logger = logging.getLogger(__name__)


class ClientHandler:
    """Mantiene la sesión de un cliente conectado y despacha comandos a métodos cmd_<nombre>."""

    def __init__(
        self,
        client_socket: socket.socket,
        client_addr: tuple[str, int],
    ) -> None:
        self.client_socket = client_socket
        self.client_addr = client_addr
        self.current_user: User | None = None
        self.upload_session: UploadSession | None = None
        self.is_connected: bool = True

    @property
    def is_authenticated(self) -> bool:
        """Indica si la sesión actual tiene un usuario autenticado."""
        return self.current_user is not None

    def handle_client(self) -> None:
        """Loop de atención del hilo: lee mensajes del socket y despacha cada comando."""
        try:
            while self.is_connected:
                try:
                    header, payload = recv_msg(self.client_socket)
                except (ConnectionError, EOFError):
                    self.is_connected = False
                    break
                except ProtocolError as proto_err:
                    self._send_error("protocol_error", str(proto_err))
                    self.is_connected = False
                    break
                except OSError:
                    self.is_connected = False
                    break

                self.dispatch(header, payload)
        finally:
            self.close()

    def dispatch(self, header: dict[str, Any], payload: bytes) -> None:
        """Valida la presencia de 'cmd' en el header y delega en `dispatch_command`."""
        raw_cmd = header.get("cmd")
        if not raw_cmd or not isinstance(raw_cmd, str):
            self._send_error("missing_command", "El header debe contener la clave 'cmd'.")
            return

        self.dispatch_command(raw_cmd, header, payload)

    def dispatch_command(
        self,
        cmd: str,
        header: dict[str, Any],
        payload: bytes,
    ) -> None:
        """Despacha el comando recibido a su método correspondiente `cmd_<nombre>`.

        Garantiza que una excepción dentro del comando no mate el hilo de atención.
        """
        if not cmd or not isinstance(cmd, str):
            self._send_error("missing_command", "El comando debe ser un string no vacío.")
            return

        cmd_name = cmd.strip().lower()
        method_name = f"cmd_{cmd_name}"
        handler_method = getattr(self, method_name, None)

        if not callable(handler_method):
            self._send_error("unknown_command", f"Comando '{cmd}' no reconocido.")
            return

        try:
            handler_method(header, payload)
        except Exception as exc:
            logger.exception("Error ejecutando comando %s para %s: %s", cmd, self.client_addr, exc)
            self._send_error("internal_error", str(exc))

    def cmd_bye(self, header: dict[str, Any], payload: bytes) -> None:
        """Comando BYE: responde OK y solicita la desconexión limpia."""
        send_msg(self.client_socket, {"status": "OK", "message": "bye"})
        self.is_connected = False

    def _send_error(self, error_code: str, message: str) -> None:
        """Envía una respuesta de error al cliente."""
        try:
            send_msg(
                self.client_socket,
                {"status": "ERROR", "error": error_code, "message": message},
            )
        except OSError:
            self.is_connected = False

    def close(self) -> None:
        """Cierra el socket y libera recursos asociados."""
        self.is_connected = False
        try:
            self.client_socket.close()
        except OSError:
            pass
