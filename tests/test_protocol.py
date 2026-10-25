"""Tests para el protocolo de mensajería sync y async (common/protocol.py)."""

import json
import socket
import struct
import threading
import unittest

from common.protocol import ProtocolError, _recv_exact, send_msg


class TestSendMsgSync(unittest.TestCase):
    """Pruebas para Issue #13 / GitHub #11: Envío de mensajes (sync)."""

    def setUp(self) -> None:
        self.server_sock, self.client_sock = socket.socketpair()
        self.server_sock.settimeout(2.0)
        self.client_sock.settimeout(2.0)

    def tearDown(self) -> None:
        self.server_sock.close()
        self.client_sock.close()

    def test_send_msg_formats_prefix_header_and_payload(self) -> None:
        header = {"cmd": "LOGIN", "username": "fran"}
        payload = b"binary-data"

        send_msg(self.client_sock, header, payload)

        prefix_raw = self.server_sock.recv(4)
        self.assertEqual(len(prefix_raw), 4)
        header_len = struct.unpack("!I", prefix_raw)[0]

        header_raw = self.server_sock.recv(header_len)
        self.assertEqual(len(header_raw), header_len)

        parsed_header = json.loads(header_raw.decode("utf-8"))
        self.assertEqual(parsed_header["cmd"], "LOGIN")
        self.assertEqual(parsed_header["username"], "fran")
        self.assertEqual(parsed_header["size"], len(payload))

        payload_raw = self.server_sock.recv(len(payload))
        self.assertEqual(payload_raw, payload)

    def test_send_msg_defaults_to_empty_payload(self) -> None:
        header = {"cmd": "LIST"}
        send_msg(self.client_sock, header)

        prefix_raw = self.server_sock.recv(4)
        header_len = struct.unpack("!I", prefix_raw)[0]
        header_raw = self.server_sock.recv(header_len)

        parsed_header = json.loads(header_raw.decode("utf-8"))
        self.assertEqual(parsed_header["cmd"], "LIST")
        self.assertEqual(parsed_header["size"], 0)


class TestRecvExactSync(unittest.TestCase):
    """Pruebas para Issue #14 / GitHub #12: Recepción exacta de bytes (sync)."""

    def setUp(self) -> None:
        self.server_sock, self.client_sock = socket.socketpair()
        self.server_sock.settimeout(2.0)
        self.client_sock.settimeout(2.0)

    def tearDown(self) -> None:
        self.server_sock.close()
        self.client_sock.close()

    def test_recv_exact_zero_bytes(self) -> None:
        self.assertEqual(_recv_exact(self.server_sock, 0), b"")

    def test_recv_exact_reads_complete_data(self) -> None:
        self.client_sock.sendall(b"1234567890")
        result = _recv_exact(self.server_sock, 10)
        self.assertEqual(result, b"1234567890")

    def test_recv_exact_handles_fragmented_delivery(self) -> None:
        expected = b"fragmented-payload-test"

        def sender() -> None:
            for byte in expected:
                self.client_sock.sendall(bytes([byte]))

        thread = threading.Thread(target=sender)
        thread.start()
        result = _recv_exact(self.server_sock, len(expected))
        thread.join()

        self.assertEqual(result, expected)

    def test_recv_exact_raises_connection_error_on_premature_close(self) -> None:
        self.client_sock.sendall(b"123")
        self.client_sock.close()

        with self.assertRaises(ConnectionError):
            _recv_exact(self.server_sock, 10)


if __name__ == "__main__":
    unittest.main()
