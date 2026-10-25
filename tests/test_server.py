"""Tests para el núcleo del servidor TCP multi-hilo (server/)."""

import socket
import unittest

from server.server import TCPServer


class TestTCPServerListeningSocket(unittest.TestCase):
    """Pruebas para Issue #19 / GitHub #16: Socket de escucha TCP con SO_REUSEADDR."""

    def test_create_listening_socket_sets_reuseaddr(self) -> None:
        server = TCPServer(host="127.0.0.1", port=0)
        sock = server.create_server_socket()
        try:
            # Verifica que SO_REUSEADDR esté activo
            reuse_addr = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
            self.assertNotEqual(reuse_addr, 0)
        finally:
            sock.close()

    def test_restarting_server_socket_on_same_port_does_not_fail(self) -> None:
        """Verifica que al cerrar y reabrir en el mismo puerto no ocurra 'Address already in use'."""
        # Reserva un puerto efímero libre
        probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe_sock.bind(("127.0.0.1", 0))
        assigned_port = probe_sock.getsockname()[1]
        probe_sock.close()

        server1 = TCPServer(host="127.0.0.1", port=assigned_port)
        sock1 = server1.create_server_socket()
        sock1.close()

        # Reabrir en el mismo puerto inmediatamente
        server2 = TCPServer(host="127.0.0.1", port=assigned_port)
        sock2 = server2.create_server_socket()
        try:
            self.assertEqual(sock2.getsockname()[1], assigned_port)
        finally:
            sock2.close()


if __name__ == "__main__":
    unittest.main()
