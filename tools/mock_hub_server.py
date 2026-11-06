"""Minimal mock of the Ultralytics HUB API (api.ultralytics.com) reconstructed from hub-sdk 0.0.25.

Logs every request (method, path, headers of interest, body shape) as JSON lines to stdout/--log.
Used only to observe what the real client sends; it does not contact Ultralytics.
"""
import argparse, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VALID_KEY = "test0000000000000000000000000000000000000000"[:42]
MODEL = {"id": "MODEL123", "status": "new", "has_last_weights": False, "is_pretrained": True,
         "weights": "https://example.invalid/best.pt", "cfg": "yolo11n.yaml", "data": "https://example.invalid/data.zip",
         "train_args": {"data": "https://example.invalid/data.zip", "epochs": 3, "imgsz": 640, "batch": 16},
         "batch_size": 16, "epochs": 3, "imgsz": 640, "patience": 100, "device": "", "cache": "ram"}
LOCK = threading.Lock()

class H(BaseHTTPRequestHandler):
    log_file = None
    def log_message(self, *a): pass
    def _reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _handle(self):
        n = int(self.headers.get("content-length", 0) or 0)
        body = self.rfile.read(n) if n else b""
        ctype = self.headers.get("content-type", "")
        rec = {"method": self.command, "path": self.path, "x-api-key": self.headers.get("x-api-key"),
               "authorization": self.headers.get("authorization"), "content-type": ctype.split(";")[0], "bytes": len(body)}
        if ctype.startswith("application/json"):
            rec["json"] = json.loads(body or b"null")
        elif ctype.startswith("multipart/form-data"):
            rec["multipart_fields"] = sorted({p.split(b'"')[0].decode() for p in body.split(b'name="')[1:]})
        with LOCK:
            line = json.dumps(rec); print(line, flush=True)
            if self.log_file: open(self.log_file, "a").write(line + "\n")
        key = self.headers.get("x-api-key")
        p = self.path.split("?")[0]
        if p == "/v1/auth":
            return self._reply(200, {"success": key == VALID_KEY})
        if key != VALID_KEY:
            return self._reply(401, {"message": "Unauthorized"})
        if p.startswith("/v1/agent/heartbeat/models/"):
            return self._reply(200, {"data": {"agentId": "AGENT-1"}})
        if p == "/v1/models" and self.command == "POST":
            return self._reply(200, {"data": {"id": "MODEL123"}})
        if p.startswith("/v1/models/MODEL123"):
            return self._reply(200, {"data": dict(MODEL)})
        if p.startswith("/v1/users/") or p.startswith("/v1/teams/"):
            return self._reply(200, {"data": {"id": p.rsplit("/", 1)[1], "name": "demo"}})
        if p in ("/v1/models", "/v1/datasets", "/v1/projects"):
            return self._reply(200, {"data": {"results": [{"id": "A"}], "total": 1, "lastRecordId": None}})
        return self._reply(404, {"message": "not found"})
    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _handle

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8787); ap.add_argument("--log")
    a = ap.parse_args(); H.log_file = a.log
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
