import os
import hmac
import hashlib
import json
from http.server import BaseHTTPRequestHandler
from pymongo import MongoClient

MONGO_URI      = os.environ.get("MONGO_URI", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY     = os.environ.get("SECRET_KEY", "changeme")

_client = None
def get_vis_col():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client["yt_uploader_bot"]["visibility"]

def make_token(pw: str) -> str:
    return hmac.new(SECRET_KEY.encode(), pw.encode(), hashlib.sha256).hexdigest()

def valid_token(token: str) -> bool:
    return hmac.compare_digest(token, make_token(ADMIN_PASSWORD))

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        token = self.headers.get("X-Admin-Token", "")
        if not valid_token(token):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data   = json.loads(body)
            key    = data.get("key")
            hidden = data.get("hidden")
            if not key:
                raise ValueError("key required")
            col = get_vis_col()
            col.update_one({"_id": key}, {"$set": {"hidden": hidden}}, upsert=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")
        self.end_headers()

    def log_message(self, format, *args):
        pass
