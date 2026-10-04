"""Loopback-only synthetic browser fixture; never contacts GitHub."""

import argparse
import json
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class FixtureServer(ThreadingHTTPServer):
    def __init__(self, port):
        super().__init__(("127.0.0.1", port), FixtureHandler)
        self.cookie_name = "personalized_usage_fixture_" + secrets.token_hex(6)
        self.sessions = {}
        self.revision = 0


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        # Requests contain only fixture data; still avoid logging cookie headers.
        pass

    def respond(self, status, body="", headers=None):
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def html(self, heading, body=""):
        return (
            "<!doctype html><html><head><title>Usage browser fixture</title></head>"
            "<body><p>SYNTHETIC TEST DATA ONLY</p><h1>" + heading + "</h1>"
            + body + "</body></html>"
        )

    def identity(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        cookie = cookies.get(self.server.cookie_name)
        return self.server.sessions.get(cookie.value) if cookie else None

    def session_state(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        cookie = cookies.get(self.server.cookie_name)
        return {
            "cookiePresent": bool(cookie and cookie.value),
            "authenticated": self.identity() is not None,
        }

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/fixture/health":
            self.respond(200, json.dumps({"fixture": "personalized-usage", "synthetic": True}))
        elif path == "/fixture/session-state":
            self.respond(200, json.dumps(self.session_state()))
        elif path == "/fixture/login":
            self.respond(200, self.html(
                "Fixture sign in",
                '<form method="post" action="/fixture/sign-in">'
                '<button>Sign in as demo-user</button></form>'
                '<form method="post" action="/fixture/wrong-account">'
                '<button>Sign in as other-demo-user</button></form>',
            ))
        elif path == "/fixture/usage":
            user = self.identity()
            if not user:
                self.respond(302, headers={"Location": "/fixture/login"})
                return
            self.server.revision += 1
            self.respond(200, self.html(
                "Copilot settings",
                '<span>Usage this cycle</span>'
                '<div hidden><h4>Usage this cycle</h4></div>'
                f'<p id="identity">Signed in as {user}</p>'
                '<p id="credits">25 / 100 AI credits</p>'
                f'<p id="revision">{self.server.revision}</p>'
                '<form method="post" action="/fixture/revoke">'
                '<button>Revoke fixture session</button></form>'
                '<form method="post" action="/fixture/challenge">'
                '<button>Require fixture verification</button></form>',
            ))
        elif path == "/fixture/no-card":
            if not self.identity():
                self.respond(302, headers={"Location": "/fixture/login"})
                return
            self.respond(200, self.html(
                "Copilot settings", f'<p id="identity">Signed in as {self.identity()}</p>'
            ))
        elif path == "/fixture/verification":
            self.respond(200, self.html(
                "Fixture verification required",
                '<form method="post" action="/fixture/sign-in">'
                '<button>Complete fixture verification</button></form>',
            ))
        elif path in ("/fixture/forbidden", "/fixture/not-found", "/fixture/unavailable"):
            code = {"/fixture/forbidden": 403, "/fixture/not-found": 404,
                    "/fixture/unavailable": 503}[path]
            self.respond(code, self.html(f"Fixture HTTP {code}"))
        elif path == "/fixture/cleanup":
            self.respond(200, self.html(
                "Fixture cleanup",
                '<form method="post" action="/fixture/reset">'
                '<button>Clear synthetic fixture state</button></form>',
            ))
        else:
            self.respond(404, self.html("Fixture not found"))

    def do_POST(self):
        path = urlsplit(self.path).path
        if path in ("/fixture/sign-in", "/fixture/wrong-account"):
            token = secrets.token_hex(16)
            self.server.sessions[token] = (
                "demo-user" if path == "/fixture/sign-in" else "other-demo-user"
            )
            self.respond(303, headers={
                "Location": "/fixture/usage",
                "Set-Cookie": (
                    f"{self.server.cookie_name}={token}; Path=/fixture; "
                    "HttpOnly; SameSite=Strict; Max-Age=300"
                ),
            })
        elif path in ("/fixture/revoke", "/fixture/challenge"):
            # Invalidate on the server while leaving the synthetic cookie present.
            self.server.sessions.clear()
            self.respond(303, headers={
                "Location": "/fixture/verification" if path.endswith("challenge")
                else "/fixture/usage"
            })
        elif path == "/fixture/reset":
            self.server.sessions.clear()
            self.respond(200, self.html("Synthetic state cleared"), {
                "Set-Cookie": f"{self.server.cookie_name}=; Path=/fixture; Max-Age=0"
            })
        else:
            self.respond(404, self.html("Fixture not found"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    with FixtureServer(args.port) as server:
        print(f"http://127.0.0.1:{server.server_port}/fixture/login", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
