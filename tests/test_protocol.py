"""Tests para el protocolo de mensajería sync y async (common/protocol.py)."""

import json
import socket
import struct
import unittest

from common.protocol import ProtocolError, send_msg


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


if __name__ == "__main__":
    unittest.main()
