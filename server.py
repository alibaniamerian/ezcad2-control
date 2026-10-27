"""Standalone EZCAD2 TCP experiment; Python standard library only."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socket
import socketserver
import threading
import time

LOG = logging.getLogger("ezcad2")
ENDINGS = {"none": b"", "crlf": b"\r\n", "lf": b"\n", "null": b"\0"}


def log_bytes(direction, peer, data):
    LOG.info("%s peer=%s bytes=%d text=%r HEX=%s", direction, peer,
             len(data), data.decode("ascii", errors="backslashreplace"), data.hex(" "))


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    # Avoid sharing an occupied port on Windows.
    allow_reuse_address = False

    def __init__(self, address, response="A1B2", ending="none", timeout=10.0,
                 gap=0.2, keep_open=False, delimiter=None):
        self.lock = threading.Lock()
        self.ending = ENDINGS[ending]
        self.set_response(response)
        self.timeout, self.gap = timeout, gap
        self.keep_open, self.delimiter = keep_open, delimiter
        super().__init__(address, Handler)

    def set_response(self, text):
        payload = text.encode("ascii", errors="strict")
        if not payload or len(payload) > 4096:
            raise ValueError("Response must contain 1..4096 ASCII bytes")
        with self.lock:
            self.payload = payload + self.ending

    def response(self):
        with self.lock:
            return self.payload


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        peer = "%s:%s" % self.client_address
        LOG.info("CONNECTED peer=%s", peer)
        pending = b""
        deadline = time.monotonic() + self.server.timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    LOG.warning("TIMEOUT peer=%s incomplete=%d", peer, len(pending))
                    return
                self.request.settimeout(min(remaining, self.server.gap)
                                        if pending and self.server.delimiter is None else remaining)
                try:
                    chunk = self.request.recv(4096)
                except socket.timeout:
                    if pending and self.server.delimiter is None:
                        chunk = None  # Experimental idle-gap framing.
                    else:
                        LOG.warning("TIMEOUT peer=%s incomplete=%d", peer, len(pending))
                        return
                if chunk == b"":
                    if pending and self.server.delimiter is None:
                        self.reply(peer, pending)
                    elif pending:
                        LOG.warning("Incomplete delimited request peer=%s", peer)
                    return
                if chunk:
                    log_bytes("RX", peer, chunk)
                    pending += chunk
                    if len(pending) > 65536:
                        LOG.warning("Request buffer limit exceeded peer=%s", peer)
                        return
                if self.server.delimiter is None:
                    if chunk is not None:
                        continue
                    frames, pending = [pending], b""
                else:
                    parts = pending.split(self.server.delimiter)
                    frames, pending = parts[:-1], parts[-1]
                for frame in frames:
                    self.reply(peer, frame)
                    if not self.server.keep_open:
                        return
                    deadline = time.monotonic() + self.server.timeout
        except OSError as exc:
            LOG.warning("NETWORK ERROR peer=%s: %s", peer, exc)
        finally:
            LOG.info("DISCONNECTED peer=%s", peer)

    def reply(self, peer, frame):
        LOG.info("REQUEST peer=%s assembled_bytes=%d", peer, len(frame))
        payload = self.server.response()
        self.request.settimeout(self.server.timeout)
        self.request.sendall(payload)
        log_bytes("TX", peer, payload)


def positive(value):
    number = float(value)
    if not 0 < number < 86400:
        raise argparse.ArgumentTypeError("Must be > 0 and < 86400")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=1000)
    parser.add_argument("--response", default="A1B2")
    parser.add_argument("--ending", choices=ENDINGS, default="none")
    parser.add_argument("--timeout", type=positive, default=10)
    parser.add_argument("--gap", type=positive, default=0.2)
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--request-ending", choices=["crlf", "lf", "null"])
    parser.add_argument("--log", default="logs/server.log")
    args = parser.parse_args()
    try:
        Path(args.log).parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                            handlers=[logging.StreamHandler(), RotatingFileHandler(
                                args.log, maxBytes=5_000_000, backupCount=5, encoding="utf-8")])
        with Server((args.host, args.port), args.response, args.ending, args.timeout,
                    args.gap, args.keep_open, ENDINGS.get(args.request_ending)) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            LOG.info("LISTENING %s; framing=%s; keep_open=%s", server.server_address,
                     args.request_ending or "EXPERIMENTAL idle gap", args.keep_open)
            print("Commands: /set TEXT, /show, /quit. Plain text also updates response.")
            try:
                while True:
                    value = input()
                    if value == "/quit":
                        break
                    if value == "/show":
                        log_bytes("CURRENT", "console", server.response())
                        continue
                    try:
                        server.set_response(value[5:] if value.startswith("/set ") else value)
                        log_bytes("UPDATED", "console", server.response())
                    except (UnicodeError, ValueError) as exc:
                        LOG.warning("Response unchanged: %s", exc)
            except (EOFError, KeyboardInterrupt):
                pass
            finally:
                server.shutdown()
                worker.join()
                LOG.info("STOPPED")
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print("Cannot start server:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
