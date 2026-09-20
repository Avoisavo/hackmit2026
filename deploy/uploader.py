#!/usr/bin/env python3
"""Tiny upload receiver so the face can be updated over Wi-Fi, with no cable.

Runs as the normal login user -- needs no root, and no change to adbd, which on
this board is wired to the USB gadget and cannot listen on TCP.

    PORT=8081 FACE_TOKEN=<token> python3 deploy/uploader.py

Endpoints (every one needs `X-Face-Token: <token>`):
    POST /upload?path=web/rabbit.js   body = file bytes   -> writes the file, fsyncs
    POST /restart                                          -> restarts the face server
    GET  /ping                                             -> {"ok": true}

Writes are confined to the face directory; `..` and absolute paths are refused.
"""
import http.server
import json
import os
import pathlib
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(os.environ.get("FACE_ROOT", pathlib.Path(__file__).resolve().parent.parent)).resolve()
PORT = int(os.environ.get("PORT", "8081"))
TOKEN = os.environ.get("FACE_TOKEN", "")

if not TOKEN:
    sys.exit("refusing to start without FACE_TOKEN -- anyone on the Wi-Fi could overwrite the face")


def safe_target(rel):
    """Resolve rel inside ROOT, or return None if it escapes."""
    if not rel or rel.startswith("/") or "\x00" in rel:
        return None
    target = (ROOT / rel).resolve()
    if target != ROOT and ROOT not in target.parents:
        return None
    return target


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        if self.headers.get("X-Face-Token") == TOKEN:
            return True
        self._json(403, {"error": "bad or missing X-Face-Token"})
        return False

    def do_GET(self):
        if urllib.parse.urlparse(self.path).path != "/ping":
            return self._json(404, {"error": "not found"})
        if not self._authed():
            return
        self._json(200, {"ok": True, "root": str(ROOT)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if not self._authed():
            return

        if u.path == "/restart":
            subprocess.run(["pkill", "-f", "robotdog-face/server.py"], check=False)
            subprocess.Popen(
                ["setsid", "python3", str(ROOT / "server.py")],
                cwd=str(ROOT),
                env={**os.environ, "PORT": "8080"},
                stdout=open("/tmp/robotdog-face.log", "ab"),
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return self._json(200, {"ok": True, "restarted": True})

        if u.path != "/upload":
            return self._json(404, {"error": "not found"})

        rel = urllib.parse.parse_qs(u.query).get("path", [""])[0]
        target = safe_target(rel)
        if target is None:
            return self._json(400, {"error": "path escapes the face directory"})

        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if n <= 0 or n > 8 * 1024 * 1024:
            return self._json(400, {"error": "empty body, or larger than 8 MB"})

        data = self.rfile.read(n)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")

        # The board loses unflushed writes when it reboots or browns out, which
        # has already cost a full deploy here. Write, fsync, rename, fsync dir.
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        dirfd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)

        self._json(200, {"ok": True, "path": rel, "bytes": len(data)})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("uploader on 0.0.0.0:%d, root=%s" % (PORT, ROOT), flush=True)
    srv.serve_forever()
