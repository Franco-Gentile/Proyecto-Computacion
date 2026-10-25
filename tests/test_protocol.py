"""Tests para el protocolo de mensajería sync y async (common/protocol.py)."""

import asyncio
import json
import socket
import struct
import threading
import unittest

from common.protocol import (
    ProtocolError,
    _recv_exact,
    async_recv_msg,
    async_send_msg,
    recv_msg,
    send_msg,
)


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


class TestRecvMsgSync(unittest.TestCase):
    """Pruebas para Issue #15 / GitHub #13: Recepción de mensajes (sync)."""

    def setUp(self) -> None:
        self.server_sock, self.client_sock = socket.socketpair()
        self.server_sock.settimeout(2.0)
        self.client_sock.settimeout(2.0)

    def tearDown(self) -> None:
        self.server_sock.close()
        self.client_sock.close()

    def test_recv_msg_roundtrip(self) -> None:
        original_header = {"cmd": "PLAY", "video_id": "vid-123", "quality": 720}
        original_payload = b"segment-payload-bytes"

        send_msg(self.client_sock, original_header, original_payload)
        header, payload = recv_msg(self.server_sock)

        self.assertEqual(header["cmd"], "PLAY")
        self.assertEqual(header["video_id"], "vid-123")
        self.assertEqual(header["quality"], 720)
        self.assertEqual(header["size"], len(original_payload))
        self.assertEqual(payload, original_payload)

    def test_recv_msg_with_empty_payload(self) -> None:
        send_msg(self.client_sock, {"cmd": "STATUS"})
        header, payload = recv_msg(self.server_sock)

        self.assertEqual(header["cmd"], "STATUS")
        self.assertEqual(header["size"], 0)
        self.assertEqual(payload, b"")

    def test_recv_msg_raises_protocol_error_on_invalid_json(self) -> None:
        bad_header_bytes = b"not-a-valid-json{"
        prefix = struct.pack("!I", len(bad_header_bytes))
        self.client_sock.sendall(prefix + bad_header_bytes)

        with self.assertRaises(ProtocolError):
            recv_msg(self.server_sock)

    def test_recv_msg_raises_protocol_error_on_non_dict_json(self) -> None:
        non_dict_header = b"[1, 2, 3]"
        prefix = struct.pack("!I", len(non_dict_header))
        self.client_sock.sendall(prefix + non_dict_header)

        with self.assertRaises(ProtocolError):
            recv_msg(self.server_sock)

    def test_recv_msg_raises_protocol_error_on_header_too_large(self) -> None:
        prefix = struct.pack("!I", 70000)
        self.client_sock.sendall(prefix)

        with self.assertRaises(ProtocolError):
            recv_msg(self.server_sock)

    def test_recv_msg_rejects_boolean_or_negative_size(self) -> None:
        for invalid_size in (True, False, -5, "10"):
            with self.subTest(size=invalid_size):
                s_sock, c_sock = socket.socketpair()
                s_sock.settimeout(2.0)
                c_sock.settimeout(2.0)
                try:
                    raw_header = json.dumps({"cmd": "TEST", "size": invalid_size}).encode("utf-8")
                    c_sock.sendall(struct.pack("!I", len(raw_header)) + raw_header)
                    with self.assertRaises(ProtocolError):
                        recv_msg(s_sock)
                finally:
                    s_sock.close()
                    c_sock.close()


class TestAsyncProtocol(unittest.IsolatedAsyncioTestCase):
    """Pruebas para Issue #16 / GitHub #14: Envío y recepción async."""

    async def test_async_send_and_recv_roundtrip(self) -> None:
        server_sock, client_sock = socket.socketpair()
        reader_s, writer_s = await asyncio.open_connection(sock=server_sock)
        reader_c, writer_c = await asyncio.open_connection(sock=client_sock)

        try:
            header = {"cmd": "UPLOAD_CHUNK", "offset": 1024}
            payload = b"chunk-bytes-data-12345"

            await async_send_msg(writer_c, header, payload)
            received_header, received_payload = await async_recv_msg(reader_s)

            self.assertEqual(received_header["cmd"], "UPLOAD_CHUNK")
            self.assertEqual(received_header["offset"], 1024)
            self.assertEqual(received_header["size"], len(payload))
            self.assertEqual(received_payload, payload)
        finally:
            writer_s.close()
            writer_c.close()
            await asyncio.gather(
                writer_s.wait_closed(),
                writer_c.wait_closed(),
                return_exceptions=True,
            )

    async def test_sync_send_to_async_recv_compatibility(self) -> None:
        s_async, c_sync = socket.socketpair()
        c_sync.settimeout(2.0)
        reader_s, writer_s = await asyncio.open_connection(sock=s_async)

        try:
            header = {"cmd": "VIDEO_INFO", "video_id": "abc-456"}
            payload = b""

            send_msg(c_sync, header, payload)
            received_header, received_payload = await async_recv_msg(reader_s)

            self.assertEqual(received_header["cmd"], "VIDEO_INFO")
            self.assertEqual(received_header["video_id"], "abc-456")
            self.assertEqual(received_payload, b"")
        finally:
            writer_s.close()
            await asyncio.gather(writer_s.wait_closed(), return_exceptions=True)
            c_sync.close()

    async def test_async_send_to_sync_recv_compatibility(self) -> None:
        s_sync, c_async = socket.socketpair()
        s_sync.settimeout(2.0)
        reader_c, writer_c = await asyncio.open_connection(sock=c_async)

        try:
            header = {"cmd": "SEGMENT", "index": 3}
            payload = b"mpegts-segment-bytes"

            await async_send_msg(writer_c, header, payload)
            received_header, received_payload = recv_msg(s_sync)

            self.assertEqual(received_header["cmd"], "SEGMENT")
            self.assertEqual(received_header["index"], 3)
            self.assertEqual(received_payload, payload)
        finally:
            writer_c.close()
            await asyncio.gather(writer_c.wait_closed(), return_exceptions=True)
            s_sync.close()

    async def test_async_recv_raises_connection_error_on_incomplete_read(self) -> None:
        server_sock, client_sock = socket.socketpair()
        reader_s, writer_s = await asyncio.open_connection(sock=server_sock)
        _, writer_c = await asyncio.open_connection(sock=client_sock)

        try:
            # Envía solo 2 bytes del prefijo de 4 bytes y cierra
            writer_c.write(b"\x00\x01")
            await writer_c.drain()
            writer_c.close()
            await writer_c.wait_closed()

            with self.assertRaises(ConnectionError):
                await async_recv_msg(reader_s)
        finally:
            writer_s.close()
            await asyncio.gather(writer_s.wait_closed(), return_exceptions=True)

    async def test_async_recv_raises_protocol_error_on_invalid_header(self) -> None:
        server_sock, client_sock = socket.socketpair()
        reader_s, writer_s = await asyncio.open_connection(sock=server_sock)
        _, writer_c = await asyncio.open_connection(sock=client_sock)

        try:
            bad_json = b"{corrupt_json"
            writer_c.write(struct.pack("!I", len(bad_json)) + bad_json)
            await writer_c.drain()

            with self.assertRaises(ProtocolError):
                await async_recv_msg(reader_s)
        finally:
            writer_s.close()
            writer_c.close()
            await asyncio.gather(
                writer_s.wait_closed(),
                writer_c.wait_closed(),
                return_exceptions=True,
            )

    async def test_async_recv_raises_protocol_error_on_oversized_header(self) -> None:
        server_sock, client_sock = socket.socketpair()
        reader_s, writer_s = await asyncio.open_connection(sock=server_sock)
        _, writer_c = await asyncio.open_connection(sock=client_sock)

        try:
            writer_c.write(struct.pack("!I", 70000))
            await writer_c.drain()

            with self.assertRaises(ProtocolError):
                await async_recv_msg(reader_s)
        finally:
            writer_s.close()
            writer_c.close()
            await asyncio.gather(
                writer_s.wait_closed(),
                writer_c.wait_closed(),
                return_exceptions=True,
            )


class TestProtocolEdgeCasesAndStress(unittest.TestCase):
    """Pruebas adicionales para Issue #17 / GitHub #15: Edge cases, payloads grandes y streams continuos."""

    def setUp(self) -> None:
        self.server_sock, self.client_sock = socket.socketpair()
        self.server_sock.settimeout(5.0)
        self.client_sock.settimeout(5.0)

    def tearDown(self) -> None:
        self.server_sock.close()
        self.client_sock.close()

    def test_completely_empty_message(self) -> None:
        """Mensaje con header vacío y payload vacío."""
        send_msg(self.client_sock, {})
        header, payload = recv_msg(self.server_sock)
        self.assertEqual(header, {"size": 0})
        self.assertEqual(payload, b"")

    def test_large_payload_transfer(self) -> None:
        """Envío y recepción de payload binario de 2 MiB."""
        large_payload = b"X" * (2 * 1024 * 1024)
        header = {"cmd": "UPLOAD_CHUNK", "seq": 1}

        send_msg(self.client_sock, header, large_payload)
        received_header, received_payload = recv_msg(self.server_sock)

        self.assertEqual(received_header["size"], len(large_payload))
        self.assertEqual(len(received_payload), len(large_payload))
        self.assertEqual(received_payload, large_payload)

    def test_multiple_consecutive_messages_in_stream(self) -> None:
        """Varios mensajes enviados en ráfaga sobre el mismo socket."""
        messages = [
            ({"cmd": "MSG_1", "id": 1}, b"payload_one"),
            ({"cmd": "MSG_2", "id": 2}, b""),
            ({"cmd": "MSG_3", "id": 3}, b"payload_three_longer_data"),
            ({"cmd": "BYE"}, b""),
        ]

        for h, p in messages:
            send_msg(self.client_sock, h, p)

        for expected_h, expected_p in messages:
            h, p = recv_msg(self.server_sock)
            self.assertEqual(h["cmd"], expected_h["cmd"])
            self.assertEqual(p, expected_p)

    def test_connection_severed_during_payload(self) -> None:
        """Corte de socket a mitad de transmisión del payload."""
        header = {"cmd": "UPLOAD_CHUNK"}
        payload = b"1234567890"

        header_bytes = json.dumps({"cmd": "UPLOAD_CHUNK", "size": len(payload)}).encode("utf-8")
        prefix = struct.pack("!I", len(header_bytes))
        self.client_sock.sendall(prefix + header_bytes + payload[:3])
        self.client_sock.close()

        with self.assertRaises(ConnectionError):
            recv_msg(self.server_sock)


if __name__ == "__main__":
    unittest.main()
