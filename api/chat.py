"""Vercel Python function: POST /api/chat with {"question": "..."}.

The logic lives in pipeline/chat.py. This file only reads the request and writes the
response. Settings come from environment variables on the Vercel project:

    ALLOWED_ORIGINS   comma-separated origins that may call the endpoint, for example
                      https://kathyvsinternet.github.io. Empty means every request is refused.
    CHAT_PROVIDER     name of the model provider. Unset means the endpoint answers 503.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from chat import handle_request, model_from_env  # noqa: E402

MAX_BODY_BYTES = 4096


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self._send(204, None, self.headers.get("Origin"))

    def do_POST(self):
        origin = self.headers.get("Origin")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._send(413, {"error": "too_large", "message": "The request is too large."}, origin)
            return
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "bad_request", "message": "The body is not valid JSON."}, origin)
            return
        status, payload = handle_request(
            body,
            origin,
            os.environ.get("ALLOWED_ORIGINS", ""),
            model_from_env(),
        )
        self._send(status, payload, origin)

    def _send(self, status, payload, origin=None):
        allowed = [item.strip() for item in os.environ.get("ALLOWED_ORIGINS", "").split(",") if item.strip()]
        self.send_response(status)
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if payload is not None:
            body = json.dumps(payload).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_header("Content-Length", "0")
            self.end_headers()
