import importlib.util
import http.cookiejar
import json
from pathlib import Path
import socket
import threading
import unittest
import urllib.request


spec = importlib.util.spec_from_file_location(
    "browser_fixture", Path(__file__).resolve().parent / "browser" / "fixture_server.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class BrowserFixtureTests(unittest.TestCase):
    def setUp(self):
        self.server = fixture.FixtureServer(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/fixture"
        self.client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.addCleanup(self.stop_fixture)

    def stop_fixture(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def get_state(self):
        with self.client.open(self.base + "/session-state", timeout=2) as response:
            return json.load(response)

    def post(self, path):
        with self.client.open(self.base + path, data=b"", timeout=2) as response:
            return response.read().decode("utf-8")

    def test_idle_browser_preconnect_does_not_block_health_requests(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        # Browsers may preconnect without sending an HTTP request.
        with socket.create_connection(self.server.server_address, timeout=2):
            for _ in range(2):
                with self.client.open(self.base + "/health", timeout=2) as response:
                    self.assertEqual(json.load(response), {
                        "fixture": "personalized-usage", "synthetic": True
                    })

    def test_revocation_rejects_present_cookie_and_reset_removes_it(self):
        self.assertEqual(self.get_state(), {"cookiePresent": False, "authenticated": False})
        self.post("/sign-in")
        self.assertEqual(self.get_state(), {"cookiePresent": True, "authenticated": True})
        self.post("/revoke")
        self.assertEqual(self.get_state(), {"cookiePresent": True, "authenticated": False})
        self.post("/reset")
        self.assertEqual(self.get_state(), {"cookiePresent": False, "authenticated": False})

    def test_usage_label_matches_observed_visible_span_and_hidden_heading(self):
        html = self.post("/sign-in")
        self.assertIn("<span>Usage this cycle</span>", html)
        self.assertIn("<div hidden><h4>Usage this cycle</h4></div>", html)
        self.assertNotIn("<h1>Usage this cycle</h1>", html)
        self.assertEqual(html.count("Usage this cycle"), 2)


if __name__ == "__main__":
    unittest.main()
