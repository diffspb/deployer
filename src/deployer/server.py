from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/":
            self._json(
                200,
                {
                    "service": "home-paas-deployer",
                    "status": "running",
                    "ui": "not implemented",
                },
            )
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host = os.getenv("DEPLOYER_HOST_BIND", "0.0.0.0")
    port = int(os.getenv("DEPLOYER_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
