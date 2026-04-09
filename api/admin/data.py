import os
import re
import hmac
import hashlib
import json
from http.server import BaseHTTPRequestHandler
from pymongo import MongoClient

MONGO_URI      = os.environ.get("MONGO_URI", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY     = os.environ.get("SECRET_KEY", "changeme")

_client = None
def get_col():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = _client["yt_uploader_bot"]
    return db["videos"], db["visibility"]

def make_token(pw: str) -> str:
    return hmac.new(SECRET_KEY.encode(), pw.encode(), hashlib.sha256).hexdigest()

def valid_token(token: str) -> bool:
    return hmac.compare_digest(token, make_token(ADMIN_PASSWORD))

def parse_caption(caption: str) -> dict:
    result = {"title": "", "batch": "Unknown Batch", "topic": "General"}
    for line in caption.splitlines():
        line = line.strip()
        if re.search(r'File\s*Title', line, re.I):
            val = re.split(r':\s*', line, 1)[-1].strip()
            val = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', val)
            val = re.sub(r'\[\d{3,4}p\]', '', val, flags=re.I)
            result["title"] = val.strip()
        elif re.search(r'Batch\s*Name', line, re.I):
            result["batch"] = re.split(r':\s*', line, 1)[-1].strip()
        elif re.search(r'Topic\s*Name', line, re.I):
            result["topic"] = re.split(r'[:\s]\s*', line, 1)[-1].strip()
    return result

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        token = self.headers.get("X-Admin-Token", "")
        if not valid_token(token):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
            return

        try:
            videos_col, vis_col = get_col()
            hidden_docs = list(vis_col.find({"hidden": True}))
            hidden_keys = {d["_id"] for d in hidden_docs}
            docs = list(videos_col.find({}, {"caption": 1, "yt_link": 1, "yt_id": 1}))

            batches = {}
            for doc in docs:
                caption = doc.get("caption", "")
                yt_link = doc.get("yt_link", "")
                yt_id   = doc.get("yt_id", "")
                if not yt_link or not caption:
                    continue
                p     = parse_caption(caption)
                batch = p["batch"] or "Unknown Batch"
                topic = p["topic"] or "General"
                title = p["title"] or caption[:60]
                tkey  = f"{batch}||{topic}"
                batches.setdefault(batch, {"hidden": batch in hidden_keys, "topics": {}})
                batches[batch]["topics"].setdefault(topic, {"hidden": tkey in hidden_keys, "lectures": []})
                batches[batch]["topics"][topic]["lectures"].append({"title": title, "yt_id": yt_id})

            body = json.dumps({"batches": batches}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")
        self.end_headers()

    def log_message(self, format, *args):
        pass
