"""Shared test helpers: puts src/ on the import path, fakes Ollama, writes small EPUB files."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def load_sample_builder():
    """samples/make_sample_epub.py as a module (samples/ is not a package)."""
    spec = importlib.util.spec_from_file_location("make_sample_epub", ROOT / "samples" / "make_sample_epub.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return path


class FakeOllama:
    """Stands in for Ollama on 127.0.0.1: answers POST /api/chat with ``reply`` and records each request body.

    ``reply`` is a string or a function of the request body; ``status`` other than 200 sends an Ollama-style error.
    """

    def __init__(self, reply="", status: int = 200):
        self.reply, self.status, self.requests = reply, status, []

    def __enter__(self) -> FakeOllama:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                if self.path != "/api/chat" or fake.status != 200:
                    status = 404 if self.path != "/api/chat" else fake.status
                    self._send(status, {"error": f"model '{body.get('model')}' not found"})
                    return
                content = fake.reply(body) if callable(fake.reply) else fake.reply
                self._send(200, {"model": body.get("model"), "done": True,
                                 "message": {"role": "assistant", "content": content}})

            def _send(self, status, payload):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
