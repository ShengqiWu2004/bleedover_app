"""Local HTTP server: the page, its JSON API and a live progress stream (Python standard library only).

It listens on 127.0.0.1 only and refuses requests whose Host or Origin isn't
this server, so other websites open in the browser can't drive it.
"""

import base64
import json
import mimetypes
import os
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import api
from .config import STATIC_DIR
from .viewer import Viewer

viewer = Viewer()
api.viewer_forget = viewer.forget
clients = {"open": 0, "last_seen": time.time()}      # windows connected to the progress stream
_clients_lock = threading.Lock()
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
ROOT_FILES = {"/": "index.html", "/manifest.webmanifest": "manifest.webmanifest", "/sw.js": "sw.js"}
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def viewer_overview(q: dict) -> dict:
    out = viewer.overview(api.run_folder(q["run"]), q["cycle"], q["tile"])
    return {**out, "png": _data_url(out["png"])}


def viewer_crop(q: dict) -> dict:
    out = viewer.crop(api.run_folder(q["run"]), q["cycle"], q["tile"], int(q["x"]), int(q["y"]), int(q["size"]))
    return {**out, "png": _data_url(out["png"])}


GET_JSON = {"/api/state": lambda q: api.state(), "/api/runs": api.runs, "/api/report": api.report,
            "/api/system": api.system, "/api/run/images": api.run_images,
            "/api/library": api.library_get, "/api/library/result": api.library_result,
            "/api/library/members": api.library_members,
            "/api/viewer/overview": viewer_overview, "/api/viewer/crop": viewer_crop}
POST_JSON = {"/api/browse": api.browse, "/api/inspect": api.inspect, "/api/fastq": api.resolve_fastq,
             "/api/origins": api.origins, "/api/estimate": api.estimate, "/api/run": api.run,
             "/api/report/build": api.build_report, "/api/cancel": api.cancel, "/api/prefs": api.save_prefs,
             "/api/calibrations/delete": api.delete_calibration, "/api/quit": lambda body: quit_app(),
             "/api/run-folders/remove": api.remove_run_folder,
             "/api/run/check": api.run_check, "/api/run/resume": api.resume, "/api/runs/delete": api.delete_run,
             "/api/library/save": api.library_save, "/api/library/check": api.library_check,
             "/api/library/run": api.library_run}
ERRORS = {FileNotFoundError: HTTPStatus.NOT_FOUND, ValueError: HTTPStatus.BAD_REQUEST, KeyError: HTTPStatus.BAD_REQUEST,
          RuntimeError: HTTPStatus.CONFLICT}


class Handler(BaseHTTPRequestHandler):
    server_version = "BleedoverCorrector"

    def log_message(self, fmt, *args):          # keep the terminal quiet; errors are reported below
        pass

    # ---- plumbing ------------------------------------------------------------------------------------------
    def _allowed(self) -> bool:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (origin is None or origin.split("//", 1)[-1] in hosts)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-cache")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(api.finite(data), default=str).encode(), "application/json")

    def _call(self, func, arg) -> None:
        try:
            result = func(arg)
        except tuple(ERRORS) as error:
            status = next(s for e, s in ERRORS.items() if isinstance(error, e))
            message = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
            return self._json({"error": f"missing {message!r}" if isinstance(error, KeyError) else message}, status)
        except Exception as error:
            traceback.print_exc()
            return self._json({"error": f"{type(error).__name__}: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
        if hasattr(result, "read_bytes"):                     # a file path (report figures)
            return self._send(200, result.read_bytes(), "image/png")
        self._json(result)

    # ---- routes --------------------------------------------------------------------------------------------
    def do_GET(self):
        if not self._allowed():
            return self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/events":
            return self._events()
        if url.path == "/api/report/file":
            return self._call(api.report_file, query)
        if url.path in GET_JSON:
            return self._call(GET_JSON[url.path], query)
        self._static(url.path)

    def do_POST(self):
        if not self._allowed() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        route = POST_JSON.get(urlparse(self.path).path)
        if route is None:
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
        self._call(route, body)

    def _static(self, path: str) -> None:
        name = ROOT_FILES.get(path) or (path[len("/static/"):] if path.startswith("/static/") else None)
        file = (STATIC_DIR / name).resolve() if name else None
        if file is None or STATIC_DIR.resolve() not in file.parents or not file.is_file():
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        extra = {"Content-Security-Policy": CSP} if file.suffix == ".html" else {}
        if file.name == "sw.js":
            extra["Service-Worker-Allowed"] = "/"
        self._send(200, file.read_bytes(), content_type + ("; charset=utf-8" if content_type.startswith("text") else ""),
                   extra)

    def _events(self) -> None:
        """Server-sent events: the job state whenever it changes (and every 15 s as a heartbeat)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        version = -1
        with _clients_lock:
            clients["open"] += 1
        try:
            while True:
                state = api.jobs.wait(version)
                version = state["version"]
                self.wfile.write(f"data: {json.dumps(api.finite(state), default=str)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with _clients_lock:
                clients["open"] -= 1
                clients["last_seen"] = time.time()


def quit_app() -> dict:
    """Stop any running job and exit shortly after answering."""
    api.jobs.cancel()
    threading.Timer(0.5, os._exit, args=(0,)).start()
    return {"quitting": True}


def stop_when_idle(server: ThreadingHTTPServer, seconds: float) -> None:
    """Shut the server down once no window has been connected for ``seconds`` and no job runs."""
    def watch():
        while True:
            time.sleep(30)
            idle = clients["open"] == 0 and time.time() - clients["last_seen"] > seconds
            if idle and not api.jobs.running():
                server.shutdown()
                return
    threading.Thread(target=watch, daemon=True).start()


def make_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
