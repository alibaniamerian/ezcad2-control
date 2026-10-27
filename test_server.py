import socket
import threading
import unittest
from contextlib import contextmanager

from server import Server


@contextmanager
def running(**kwargs):
    with Server(("127.0.0.1", 0), **kwargs) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


def read_to_eof(conn):
    result = b""
    while chunk := conn.recv(4096):
        result += chunk
    return result


class ServerTests(unittest.TestCase):
    def test_default_and_console_state_update(self):
        with running(gap=0.02) as server:
            for expected in (b"A1B2", b"SERIAL002"):
                server.set_response(expected.decode())
                with socket.create_connection(server.server_address, timeout=2) as conn:
                    conn.sendall(b"TCP:Give me string")
                    self.assertEqual(read_to_eof(conn), expected)

    def test_fragmented_and_coalesced_requests(self):
        with running(delimiter=b"\r\n", keep_open=True, ending="null") as server:
            with socket.create_connection(server.server_address, timeout=2) as conn:
                conn.sendall(b"TCP:Give")
                conn.sendall(b" me string\r\nnext\r\n")
                data = b""
                while len(data) < 10:
                    data += conn.recv(10 - len(data))
                self.assertEqual(data, b"A1B2\0A1B2\0")

    def test_timeout_and_reconnect(self):
        with running(timeout=0.1, gap=0.01) as server:
            with socket.create_connection(server.server_address, timeout=2) as conn:
                self.assertEqual(conn.recv(1), b"")
            with socket.create_connection(server.server_address, timeout=2) as conn:
                conn.sendall(b"retry")
                self.assertEqual(read_to_eof(conn), b"A1B2")

    def test_incomplete_delimited_request_no_response(self):
        with running(delimiter=b"\n", timeout=0.1) as server:
            with socket.create_connection(server.server_address, timeout=2) as conn:
                conn.sendall(b"partial")
                self.assertEqual(read_to_eof(conn), b"")

    def test_invalid_update_preserves_response(self):
        with running() as server:
            for invalid in ("", "فارسی", "X" * 4097):
                with self.assertRaises((ValueError, UnicodeError)):
                    server.set_response(invalid)
                self.assertEqual(server.response(), b"A1B2")


if __name__ == "__main__":
    unittest.main()
