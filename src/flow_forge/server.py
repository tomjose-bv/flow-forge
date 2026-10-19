"""HTTP front for the apps (standard library only).

    POST /<app>/actions/<action>   body {"inputs": {...}}   header X-Api-Key, optional Idempotency-Key
    GET  /<app>/events?after=<id>  -> {"events": [...], "last_id": <id>}
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from flow_forge.apps import ActionError, App


class AppServer:
    def __init__(self, apps: dict[str, App]):
        self.apps = apps
        self.log: list[dict[str, Any]] = []
        self.lock = threading.Lock()  # apps are not thread-safe; serialize all calls
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> "AppServer":
        srv = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                srv._handle(self, "GET")

            def do_POST(self):  # noqa: N802
                srv._handle(self, "POST")

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "AppServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def _handle(self, h: BaseHTTPRequestHandler, method: str) -> None:
        parts = urlsplit(h.path)
        segs = [s for s in parts.path.split("/") if s]
        with self.lock:
            status, body = self._route(h, method, segs, {k: v[-1] for k, v in parse_qs(parts.query).items()})
            self.log.append({"t": time.monotonic(), "method": method, "path": h.path, "status": status})
        payload = json.dumps(body).encode()
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(payload)))
        h.end_headers()
        h.wfile.write(payload)

    def _route(self, h, method, segs, query) -> tuple[int, Any]:
        if not segs or segs[0] not in self.apps:
            return 404, {"error": "unknown app"}
        app = self.apps[segs[0]]
        if h.headers.get("X-Api-Key") != app.api_key:
            return 401, {"error": "invalid or missing X-Api-Key"}
        if method == "GET" and segs[1:] == ["events"]:
            try:
                after = int(query.get("after", 0))
            except ValueError:
                return 400, {"error": "after must be an integer"}
            events = app.events_after(after)
            return 200, {"events": events, "last_id": events[-1]["id"] if events else after}
        if method == "POST" and len(segs) == 3 and segs[1] == "actions":
            try:
                length = int(h.headers.get("Content-Length") or 0)
                body = json.loads(h.rfile.read(length) or b"{}")
            except ValueError:
                return 400, {"error": "body must be JSON"}
            try:
                result = app.call(segs[2], body.get("inputs", {}), h.headers.get("Idempotency-Key"))
            except ActionError as e:
                return e.status, {"error": e.message}
            return 200, {"result": result}
        return 404, {"error": "not found"}
