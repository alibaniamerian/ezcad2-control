import base64
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from web_panel import Panel, Server


class FakeUI:
    def __init__(self):
        self.identity = (1, 2, 3, "Test panel.ezd")
        self.clicks = []
        self.loads = []

    def command(self, action):
        return {}, self.identity

    def click(self, action, expected):
        if self.identity != expected:
            raise RuntimeError("Target changed")
        self.clicks.append(action)

    def load_file(self, path):
        self.loads.append(path)
        return path, 1

    def fill_open_dialog(self, path, pid):
        return True


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ui = FakeUI()
        self.panel = Panel(self.ui, Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_mark_requires_ticket_and_duplicate_does_not_click_twice(self):
        self.assertFalse(self.panel.execute(dict(id="request01", action="mark"))["ok"])
        ticket = self.panel.execute(dict(id="request02", action="prepare_mark"))["ticket"]
        request = dict(id="request03", action="mark", ticket=ticket)
        self.assertTrue(self.panel.execute(request)["ok"])
        self.assertTrue(self.panel.execute(request)["ok"])
        self.assertFalse(self.panel.execute(dict(request, id="request04"))["ok"])
        self.assertEqual(self.ui.clicks, ["mark"])

    def test_changed_target_and_expired_confirmation(self):
        ticket = self.panel.execute(dict(id="request01", action="prepare_mark"))["ticket"]
        self.ui.identity = (1, 2, 3, "Other.ezd")
        self.assertFalse(self.panel.execute(dict(id="request02", action="mark", ticket=ticket))["ok"])
        ticket = self.panel.execute(dict(id="request03", action="prepare_mark"))["ticket"]
        self.panel.tickets[ticket] = (self.ui.identity, time.monotonic() - 1)
        self.assertFalse(self.panel.execute(dict(id="request04", action="mark", ticket=ticket))["ok"])
        self.assertEqual(self.ui.clicks, [])

    def test_upload_uses_generated_path_and_never_marks(self):
        request = dict(id="request01", action="load", name="../../panel.ezd",
                       content=base64.b64encode(b"test fixture").decode())
        self.assertTrue(self.panel.execute(request)["ok"])
        deadline = time.monotonic() + 2
        while self.panel.pending and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.panel.pending)
        self.assertEqual(self.ui.loads[0].parent, Path(self.temp.name))
        self.assertEqual(self.ui.loads[0].read_bytes(), b"test fixture")
        self.assertEqual(self.ui.clicks, [])

    def test_http_origin_token_host_and_readonly_status(self):
        with Server(("127.0.0.1", 0), self.panel) as server:
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                def request(method, path, headers=None, data=None):
                    conn = http.client.HTTPConnection(*server.server_address, timeout=3)
                    conn.request(method, path, body=json.dumps(data) if data else None, headers=headers or {})
                    response = conn.getresponse()
                    result = response.status, response.read()
                    conn.close()
                    return result
                self.assertEqual(request("GET", "/")[0], 200)
                self.assertEqual(request("GET", "/api/status")[0], 200)
                self.assertEqual(self.ui.clicks, [])
                headers = {"Content-Type": "application/json", "Origin": "http://evil.example",
                           "X-Panel-Token": server.token}
                data = dict(id="request01", action="red")
                self.assertEqual(request("POST", "/api/action", headers, data)[0], 403)
                headers["Origin"] = "http://" + server.authority
                headers["X-Panel-Token"] = "invalid"
                self.assertEqual(request("POST", "/api/action", headers, data)[0], 403)
                headers["X-Panel-Token"] = server.token
                self.assertEqual(request("POST", "/api/action", headers, data)[0], 200)
                self.assertEqual(request("POST", "/api/action", headers, data)[0], 200)
                self.assertEqual(self.ui.clicks, ["red"])
                self.assertEqual(request("GET", "/", {"Host": "evil.example"})[0], 403)
            finally:
                server.shutdown()
                worker.join()


if __name__ == "__main__":
    unittest.main()
