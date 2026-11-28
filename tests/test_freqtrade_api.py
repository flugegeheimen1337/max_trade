import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.freqtrade_api import ApiError, post_command

PASSWORD = "local-test-password-not-a-secret"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path == "/api/v1/token/login":
            if self.headers.get("Authorization", "").startswith("Basic "):
                self._send(200, {"access_token": "issued-token"})
                return
        if self.path == "/api/v1/pause":
            if self.headers.get("Authorization") == "Bearer issued-token":
                self._send(200, {"status": "paused"})
                return
        self._send(401, {"detail": "unauthorized"})

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def test_operator_posts_a_bearer_command_without_echoing_the_password():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = post_command(base, "freqtrade", PASSWORD, "pause")
        assert json.loads(body)["status"] == "paused"
        try:
            post_command(base, "freqtrade", PASSWORD, "missing")
        except ApiError as exc:
            assert PASSWORD not in str(exc)
        else:
            raise AssertionError("missing command should fail")
    finally:
        server.shutdown()
