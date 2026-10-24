"""A disposable loopback server with deliberate faults, never a production server."""

import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAYLOAD = bytes(range(256)) * 4 + b"range-witness-end"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def do_GET(self):
        mode = self.path.split("?", 1)[0].strip("/")
        data = b"X" if mode == "tiny" else PAYLOAD
        if mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        etag = 'W/"fixture-v1"' if mode == "weak" else '"fixture-v1"'
        validator = self.headers.get("If-Range")
        if mode == "ignored" or (validator and validator != etag and mode != "bad-if-range"):
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self._write(data)
            return
        value = self.headers.get("Range", "")
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
        if not match:
            self.send_error(400)
            return
        start_text, end_text = match.groups()
        if start_text:
            start = int(start_text)
            end = min(int(end_text), len(data) - 1) if end_text else len(data) - 1
        else:
            start = max(0, len(data) - int(end_text))
            end = len(data) - 1
        if start >= len(data):
            self.send_response(200 if mode == "bad-416" else 416)
            self.send_header("Content-Range", f"bytes */{len(data)}")
            self.end_headers()
            return
        part = data[start : end + 1]
        if mode == "corrupt" and start > 0:
            part = b"!" * len(part)
        if mode == "short":
            part = part[:-1]
        if mode == "oversized":
            part += b"!"
        self.send_response(206)
        content_range = f"bytes {start}-{end}/{len(data)}"
        if mode == "bad-range":
            content_range = "not-a-range"
        if mode == "wrong-range" and start > 0:
            content_range = f"bytes 0-{end - start}/{len(data)}"
        self.send_header("Content-Range", content_range)
        if mode == "duplicate":
            self.send_header("Content-Range", content_range)
        self.send_header("Content-Length", str(len(part)))
        if mode == "encoded":
            self.send_header("Content-Encoding", "gzip")
        if mode != "no-etag":
            self.send_header("ETag", '"changed"' if mode == "changing" and start > 0 else etag)
        self.end_headers()
        self._write(part)

    def _write(self, content):
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # A bounded probe intentionally closes an unneeded full response.


@contextmanager
def running_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
