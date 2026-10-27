"""Loopback-only web controls. Starting the server sends no machine commands."""
import argparse
import base64
import json
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
import uuid

from control_panel import WindowsUI, DEFAULT_EXE, validate_ezd

ROOT = Path(__file__).resolve().parent
MAX_BODY = 28 * 1024 * 1024


class Panel:
    def __init__(self, ui, upload_dir=None):
        self.ui = ui
        self.lock = threading.RLock()
        self.pending = False
        self.message = "آماده؛ هیچ فرمانی ارسال نشده است."
        self.selected = ""
        self.tickets = {}
        self.results = {}
        self.upload_dir = upload_dir or ROOT / "runtime" / "web_uploads"

    def status(self):
        with self.lock:
            available = {}
            title = ""
            for action in ("red", "stop", "mark"):
                try:
                    _, identity = self.ui.command(action)
                    available[action] = True
                    title = title or identity[3]
                except (RuntimeError, OSError):
                    available[action] = False
            return dict(available=available, title=title, pending=self.pending,
                        message=self.message, selected=self.selected)

    def execute(self, data):
        request_id = data.get("id", "")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
            raise ValueError("Invalid request ID")
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if request_id in self.results:
                old, response = self.results[request_id]
                if old != fingerprint:
                    raise ValueError("Request ID reused with different content")
                return response
            # Retain IDs for the process lifetime; require restart rather than unsafe eviction.
            if len(self.results) >= 10000:
                raise ValueError("Session request limit reached; restart service")
            self.results[request_id] = (fingerprint, {"ok": False, "message": "Outcome unknown; inspect EZCAD2"})
            try:
                response = self._execute(data)
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
                self.message = "خطا؛ وضعیت EZCAD2 را بررسی کنید: " + str(exc)
                response = {"ok": False, "message": str(exc)}
            self.results[request_id] = (fingerprint, response)
            return response

    def _execute(self, data):
        action = data.get("action")
        if self.pending and action != "stop":
            raise ValueError("File loading is pending. Resolve the dialog in EZCAD2 first.")
        if action == "prepare_mark":
            _, identity = self.ui.command("mark")
            token = secrets.token_urlsafe(24)
            self.tickets = {token: (identity, time.monotonic() + 30)}
            return dict(ok=True, ticket=token, title=identity[3])
        if action in ("red", "stop", "mark"):
            if action == "mark":
                ticket = self.tickets.pop(data.get("ticket", ""), None)
                if not ticket or ticket[1] < time.monotonic():
                    raise ValueError("Mark confirmation expired; confirm again")
                identity = ticket[0]
            else:
                _, identity = self.ui.command(action)
            self.tickets.clear()
            self.ui.click(action, identity)
            self.message = f"درخواست {action.upper()} ارسال شد؛ نتیجه را در EZCAD2 و دستگاه بررسی کنید."
        elif action == "load":
            self.tickets.clear()
            if data.get("path"):
                path = validate_ezd(data["path"])
                label = str(path)
            else:
                name = data.get("name", "")
                if not isinstance(name, str) or not name.lower().endswith(".ezd"):
                    raise ValueError("Select an .ezd file")
                content = base64.b64decode(data.get("content", ""), validate=True)
                if not content or len(content) > 20 * 1024 * 1024:
                    raise ValueError("File must contain 1 byte to 20 MB")
                self.upload_dir.mkdir(parents=True, exist_ok=True)
                path = self.upload_dir / (uuid.uuid4().hex + ".ezd")
                path.write_bytes(content)
                label = name
            path, pid = self.ui.load_file(path)
            self.selected = label
            self.pending = True
            self.message = "منتظر پنجره Open؛ اگر EZCAD2 سؤال ذخیره دارد، همان‌جا پاسخ دهید."
            threading.Thread(target=self.finish_load, args=(path, pid), daemon=True).start()
        else:
            raise ValueError("Unknown action")
        return dict(ok=True, message=self.message)

    def finish_load(self, path, pid):
        deadline = time.monotonic() + 120
        try:
            while time.monotonic() < deadline:
                with self.lock:
                    if self.ui.fill_open_dialog(path, pid):
                        self.message = "فایل به Open ارسال شد؛ طرح را در EZCAD2 بررسی کنید. مارکینگ شروع نشده است."
                        return
                time.sleep(0.4)
            with self.lock:
                self.message = "مهلت بارگذاری تمام شد؛ پنجره‌های EZCAD2 را بررسی کنید."
        except Exception as exc:
            with self.lock:
                self.message = "خطای بارگذاری: " + str(exc)
        finally:
            with self.lock:
                self.pending = False


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, panel):
        super().__init__(address, Handler)
        self.panel = panel
        self.token = secrets.token_urlsafe(32)
        self.authority = f"127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, value, content_type="application/json; charset=utf-8"):
        body = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, mutation=False):
        if self.headers.get("Host") != self.server.authority:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        if mutation:
            return (self.headers.get("Origin") == "http://" + self.server.authority
                    and secrets.compare_digest(self.headers.get("X-Panel-Token", ""), self.server.token))
        return True

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {"message": "Local origin required"})
        if self.path == "/api/status":
            return self.reply(200, dict(self.server.panel.status(), token=self.server.token))
        assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                  "/style.css": ("style.css", "text/css")}
        if self.path not in assets:
            return self.reply(404, {"message": "Not found"})
        filename, mime = assets[self.path]
        self.reply(200, (ROOT / "web" / filename).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        self.connection.settimeout(15)
        if not self.allowed(mutation=True):
            return self.reply(403, {"message": "Local origin and session token required"})
        if self.path != "/api/action":
            return self.reply(404, {"message": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY or self.headers.get("Content-Type") != "application/json":
                raise ValueError("Invalid request size or content type")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            self.reply(200, self.server.panel.execute(data))
        except (ValueError, OSError) as exc:
            self.reply(400, {"ok": False, "message": str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--exe", default=DEFAULT_EXE)
    args = parser.parse_args()
    with Server(("127.0.0.1", args.port), Panel(WindowsUI(args.exe))) as server:
        print(f"Open http://{server.authority} — Ctrl+C to stop web service (does not stop laser).")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
