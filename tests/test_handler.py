"""Tests para ClientHandler y despacho de comandos (server/handler.py - Issue #23)."""

import socket
import threading
import unittest

from common.protocol import recv_msg, send_msg
from server.handler import ClientHandler


class DummyCommandHandler(ClientHandler):
    """Handler de prueba que extiende ClientHandler para simular comandos."""

    def cmd_echo(self, header: dict, payload: bytes) -> None:
        send_msg(self.client_socket, {"status": "OK", "echo": header.get("msg")}, payload)

    def cmd_blow_up(self, header: dict, payload: bytes) -> None:
        raise RuntimeError("Fallo forzado dentro de comando")


class TestClientHandlerDispatch(unittest.TestCase):
    """Pruebas para Issue #23 / GitHub #18: Despacho de comandos y manejo de excepciones."""

    def setUp(self) -> None:
        self.server_sock, self.client_sock = socket.socketpair()
        self.server_sock.settimeout(3.0)
        self.client_sock.settimeout(3.0)

    def tearDown(self) -> None:
        self.server_sock.close()
        self.client_sock.close()

    def test_dispatch_known_command_succeeds(self) -> None:
        handler = DummyCommandHandler(self.server_sock, ("127.0.0.1", 12345))
        thread = threading.Thread(target=handler.handle_client, daemon=True)
        thread.start()

        send_msg(self.client_sock, {"cmd": "ECHO", "msg": "hola"})
        header, _ = recv_msg(self.client_sock)

        self.assertEqual(header["status"], "OK")
        self.assertEqual(header["echo"], "hola")

        handler.is_connected = False
        thread.join(timeout=1.0)

    def test_unknown_command_returns_error(self) -> None:
        handler = DummyCommandHandler(self.server_sock, ("127.0.0.1", 12345))
        thread = threading.Thread(target=handler.handle_client, daemon=True)
        thread.start()

        send_msg(self.client_sock, {"cmd": "NON_EXISTENT_COMMAND"})
        header, _ = recv_msg(self.client_sock)

        self.assertEqual(header["status"], "ERROR")
        self.assertEqual(header["error"], "unknown_command")

        handler.is_connected = False
        thread.join(timeout=1.0)

    def test_exception_in_command_does_not_kill_thread(self) -> None:
        """Criterio clave: Una excepción dentro de un comando no mata el hilo y permite seguir atendiendo."""
        handler = DummyCommandHandler(self.server_sock, ("127.0.0.1", 12345))
        thread = threading.Thread(target=handler.handle_client, daemon=True)
        thread.start()

        # 1. Enviar comando que lanza excepción
        send_msg(self.client_sock, {"cmd": "BLOW_UP"})
        header1, _ = recv_msg(self.client_sock)

        self.assertEqual(header1["status"], "ERROR")
        self.assertEqual(header1["error"], "internal_error")

        # 2. El hilo debe seguir vivo y responder al siguiente comando
        self.assertTrue(thread.is_alive())
        send_msg(self.client_sock, {"cmd": "ECHO", "msg": "recuperado"})
        header2, _ = recv_msg(self.client_sock)

        self.assertEqual(header2["status"], "OK")
        self.assertEqual(header2["echo"], "recuperado")

        handler.is_connected = False
        thread.join(timeout=1.0)

    def test_cmd_bye_disconnects_cleanly(self) -> None:
        handler = ClientHandler(self.server_sock, ("127.0.0.1", 12345))
        thread = threading.Thread(target=handler.handle_client, daemon=True)
        thread.start()

        send_msg(self.client_sock, {"cmd": "BYE"})
        header, _ = recv_msg(self.client_sock)

        self.assertEqual(header["status"], "OK")
        self.assertEqual(header.get("message"), "bye")
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
