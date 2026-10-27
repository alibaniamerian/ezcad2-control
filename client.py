"""Local TCP test client; does not operate EZCAD2 or hardware."""
import argparse
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1000)
    parser.add_argument("--request", default="TCP:Give me string")
    parser.add_argument("--request-ending", choices=["none", "crlf", "lf", "null"], default="none")
    parser.add_argument("--expect", default="A1B2")
    parser.add_argument("--ending", choices=["none", "crlf", "lf", "null"], default="none")
    args = parser.parse_args()
    endings = {"none": b"", "crlf": b"\r\n", "lf": b"\n", "null": b"\0"}
    try:
        request = args.request.encode("ascii") + endings[args.request_ending]
        expected = args.expect.encode("ascii") + endings[args.ending]
        with socket.create_connection((args.host, args.port), timeout=5) as conn:
            conn.sendall(request)
            print("TX", repr(request), "HEX", request.hex(" "))
            received = b""
            # Default server closes the connection: read through EOF, not one recv().
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                received += chunk
                if len(received) > 65536:
                    raise ValueError("Response too large")
        print("RX", repr(received), "HEX", received.hex(" "))
        print("PASS" if received == expected else "FAIL: unexpected response")
        return 0 if received == expected else 1
    except (OSError, ValueError, UnicodeError) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
