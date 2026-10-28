"""Tests para el núcleo del servidor TCP multi-hilo (server/)."""

import socket
import threading
import unittest

from common.protocol import recv_msg, send_msg
from server.handler import ClientHandler
from server.server import TCPServer


class TestTCPServerListeningSocket(unittest.TestCase):
    """Pruebas para el socket de escucha TCP con SO_REUSEADDR."""

    def test_create_listening_socket_sets_reuseaddr(self) -> None:
        server = TCPServer(host="127.0.0.1", port=0)
        sock = server.create_server_socket()
        try:
            reuse_addr = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
            self.assertNotEqual(reuse_addr, 0)
        finally:
            sock.close()

    def test_restarting_server_socket_on_same_port_does_not_fail(self) -> None:
        """Verifica que al cerrar y reabrir en el mismo puerto no ocurra 'Address already in use'."""
        probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe_sock.bind(("127.0.0.1", 0))
        assigned_port = probe_sock.getsockname()[1]
        probe_sock.close()

        server1 = TCPServer(host="127.0.0.1", port=assigned_port)
        sock1 = server1.create_server_socket()
        sock1.close()

        server2 = TCPServer(host="127.0.0.1", port=assigned_port)
        sock2 = server2.create_server_socket()
        try:
            self.assertEqual(sock2.getsockname()[1], assigned_port)
        finally:
            sock2.close()


class TestTCPServerThreadPerClient(unittest.TestCase):
    """Pruebas de atención concurrente de clientes y ciclo de vida del servidor."""

    def test_default_handler_factory_uses_client_handler(self) -> None:
        server = TCPServer(host="127.0.0.1", port=0)
        server.start()
        assert server.server_socket is not None
        port = server.server_socket.getsockname()[1]

        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=3.0)
            send_msg(client, {"cmd": "BYE"})
            header, _ = recv_msg(client)
            self.assertEqual(header["status"], "OK")
            self.assertEqual(header["message"], "bye")
            client.close()
        finally:
            server.stop()

    def test_two_clients_handled_in_parallel(self) -> None:
        barrier = threading.Barrier(2, timeout=5.0)
        active_thread_names: list[str] = []
        lock = threading.Lock()

        class SyncBarrierHandler:
            def __init__(self, client_sock: socket.socket, addr: tuple[str, int]) -> None:
                self.sock = client_sock
                self.addr = addr

            def handle_client(self) -> None:
                try:
                    with lock:
                        active_thread_names.append(threading.current_thread().name)
                    barrier.wait()
                    send_msg(self.sock, {"status": "OK", "thread": threading.current_thread().name})
                finally:
                    self.sock.close()

        server = TCPServer(host="127.0.0.1", port=0, handler_factory=SyncBarrierHandler)
        server.start()
        assert server.server_socket is not None
        port = server.server_socket.getsockname()[1]

        try:
            c1 = socket.create_connection(("127.0.0.1", port), timeout=3.0)
            c2 = socket.create_connection(("127.0.0.1", port), timeout=3.0)

            h1, _ = recv_msg(c1)
            h2, _ = recv_msg(c2)

            self.assertEqual(h1["status"], "OK")
            self.assertEqual(h2["status"], "OK")
            self.assertNotEqual(h1["thread"], h2["thread"])
            self.assertEqual(len(active_thread_names), 2)
            c1.close()
            c2.close()
        finally:
            server.stop()

    def test_disconnected_client_threads_and_sockets_are_cleaned_up(self) -> None:
        server = TCPServer(host="127.0.0.1", port=0)
        server.start()
        assert server.server_socket is not None
        port = server.server_socket.getsockname()[1]

        try:
            for _ in range(5):
                client = socket.create_connection(("127.0.0.1", port), timeout=3.0)
                send_msg(client, {"cmd": "BYE"})
                recv_msg(client)
                client.close()

            for t in list(server._client_threads):
                t.join(timeout=1.0)

            with server._lock:
                self.assertEqual(len(server._client_threads), 0)
                self.assertEqual(len(server._client_sockets), 0)
        finally:
            server.stop()

    def test_stop_closes_idle_clients_rapidly(self) -> None:
        import time

        server = TCPServer(host="127.0.0.1", port=0)
        server.start()
        assert server.server_socket is not None
        port = server.server_socket.getsockname()[1]

        clients = [
            socket.create_connection(("127.0.0.1", port), timeout=3.0)
            for _ in range(5)
        ]
        try:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                with server._lock:
                    if len(server._client_sockets) == 5:
                        break
                time.sleep(0.01)

            start_t = time.monotonic()
            server.stop()
            elapsed = time.monotonic() - start_t

            self.assertLess(elapsed, 1.5)
            with server._lock:
                self.assertEqual(len(server._client_threads), 0)
                self.assertEqual(len(server._client_sockets), 0)
        finally:
            for c in clients:
                c.close()

    def test_handler_factory_exception_does_not_kill_listener(self) -> None:
        calls = 0

        def flaky_factory(client_sock: socket.socket, addr: tuple[str, int]) -> ClientHandler:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("Error simulado al instanciar handler")
            return ClientHandler(client_sock, addr)

        server = TCPServer(host="127.0.0.1", port=0, handler_factory=flaky_factory)
        server.start()
        assert server.server_socket is not None
        port = server.server_socket.getsockname()[1]

        try:
            c1 = socket.create_connection(("127.0.0.1", port), timeout=3.0)
            c1.close()

            c2 = socket.create_connection(("127.0.0.1", port), timeout=3.0)
            send_msg(c2, {"cmd": "BYE"})
            header, _ = recv_msg(c2)
            self.assertEqual(header["status"], "OK")
            c2.close()
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
