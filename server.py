#!/usr/bin/env python3
"""Robot dog face: static server, emote control API, and SSE push channel.

Standard library only -- nothing to pip install, on the board or on a laptop.

    GET  /                   the fullscreen face
    GET  /gallery            every emote side by side, for tuning
    GET  /emotes             JSON list of emote names
    GET  /events             SSE stream the face page subscribes to
    POST /emote              {"name": "happy", "hold": 3}
    GET  /emote?name=happy   same thing, for curl and address bars
    GET  /health             liveness + connected face count
"""

import json
import math
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
TOOLS = os.path.join(HERE, "tools")
PORT = int(os.environ.get("PORT", "8080"))
HOST = os.environ.get("HOST", "0.0.0.0")

LEGACY_EMOTES = [
    "neutral", "happy", "excited", "curious", "sad",
    "sleepy", "surprised", "angry", "love", "boot",
]

EMOTES = ["Ready", "Watching", "Encourage", "Thinking", "Go", "Celebrate", "Rest", "Soft confused"]
VERSION = "twinkle-v2-glossy"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}

_clients = []
_lock = threading.Lock()


def broadcast(payload):
    """Push an event to every connected face page. Drops clients that stall."""
    dead = []
    with _lock:
        for q in _clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _clients.remove(q)
    return len(_clients)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "robotdog-face"

    def log_message(self, fmt, *args):
        if os.environ.get("FACE_VERBOSE"):
            super().log_message(fmt, *args)

    # -- helpers ----------------------------------------------------------
    def _send(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # Control dashboards are typically opened as a local file or from a
        # different origin than the board, so every response needs CORS
        # headers or the browser's fetch() rejects it before it ever reaches
        # this handler.
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _static(self, path):
        """Serve a file from web/ or tools/, refusing anything outside them."""
        for root in (WEB, TOOLS):
            full = os.path.normpath(os.path.join(root, path.lstrip("/")))
            if not full.startswith(root + os.sep):
                continue
            if os.path.isfile(full):
                ext = os.path.splitext(full)[1]
                with open(full, "rb") as fh:
                    self._send(200, fh.read(), MIME.get(ext, "application/octet-stream"))
                return
        self._send(404, "not found")

    def _apply_emote(self, name, hold, result=False):
        if name not in EMOTES + LEGACY_EMOTES:
            self._json(400, {"error": "unknown emote", "known": EMOTES})
            return
        if not math.isfinite(hold) or hold < 0 or hold > 86400:
            return self._json(400, {"error": "hold must be between 0 and 86400 seconds"})
        n = broadcast({"name": name, "hold": hold, "result": result})
        self._json(200, {"ok": True, "name": name, "hold": hold, "result": result, "faces": n})

    # -- SSE --------------------------------------------------------------
    def _events(self):
        q = queue.Queue(maxsize=32)
        with _lock:
            _clients.append(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    item = q.get(timeout=15)
                    self.wfile.write(("data: " + json.dumps(item) + "\n\n").encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # keeps proxies from timing us out
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _lock:
                if q in _clients:
                    _clients.remove(q)

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path

        if p in ("/", "/twinkle"):
            return self._static("twinkle-panel.html")
        if p == "/classic":
            return self._static("index.html")
        if p == "/dashboard":
            return self._static("dashboard.html")
        if p in ("/gallery", "/gallery.html"):
            return self._static("gallery.html")
        if p in ("/labv2", "/labv2.html"):
            return self._static("labv2.html")
        if p in ("/lab", "/lab.html"):
            return self._static("lab.html")
        if p == "/events":
            return self._events()
        if p == "/emotes":
            return self._json(200, {"emotes": EMOTES, "legacy_emotes": LEGACY_EMOTES})
        if p == "/health":
            with _lock:
                n = len(_clients)
            return self._json(200, {"ok": True, "faces": n, "version": VERSION})
        if p == "/emote":
            qs = parse_qs(u.query)
            name = (qs.get("name") or [""])[0]
            try:
                hold = float((qs.get("hold") or ["0"])[0])
            except ValueError:
                hold = 0
            return self._apply_emote(name, hold, (qs.get("result") or ["0"])[0] == "1")
        return self._static(p)

    def do_POST(self):
        if urlparse(self.path).path != "/emote":
            return self._send(404, "not found")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, TypeError):
            return self._json(400, {"error": "bad json"})
        if not isinstance(body, dict):
            return self._json(400, {"error": "expected a json object"})
        try:
            hold = float(body.get("hold") or 0)
        except (TypeError, ValueError):
            hold = 0
        return self._apply_emote(body.get("name"), hold, body.get("result") is True)

    def do_OPTIONS(self):
        # CORS preflight for the JSON POST /emote request from a dashboard on
        # another origin. No body needed -- just the allow headers.
        self._send(204, b"", extra={
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    print("robot dog face on http://%s:%d  (emotes: %s)" % (HOST, PORT, ", ".join(EMOTES)))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
