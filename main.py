import os
import re
import hmac
import hashlib
import json
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__, static_folder="public")

MONGO_URI = os.environ.get("MONGO_URI", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")

_client = None


def get_db():
    global _client
    if _client is None:
        from pymongo import MongoClient
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = _client["yt_uploader_bot"]
    return db["videos"], db["visibility"]


def make_token(pw: str) -> str:
    return hmac.new(SECRET_KEY.encode(), pw.encode(), hashlib.sha256).hexdigest()


def valid_token(token: str) -> bool:
    expected = make_token(ADMIN_PASSWORD)
    return hmac.compare_digest(token, expected)


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


@app.route("/api/data", methods=["GET"])
def api_data():
    try:
        videos_col, vis_col = get_db()
        hidden_docs = list(vis_col.find({"hidden": True}))
        hidden_keys = {d["_id"] for d in hidden_docs}
        docs = list(videos_col.find({}, {"caption": 1, "yt_link": 1, "yt_id": 1}))

        batches = {}
        for doc in docs:
            caption = doc.get("caption", "")
            yt_link = doc.get("yt_link", "")
            yt_id = doc.get("yt_id", "")
            if not yt_link or not caption:
                continue
            p = parse_caption(caption)
            batch = p["batch"] or "Unknown Batch"
            topic = p["topic"] or "General"
            title = p["title"] or caption[:60]
            if batch in hidden_keys or f"{batch}||{topic}" in hidden_keys:
                continue
            batches.setdefault(batch, {}).setdefault(topic, []).append(
                {"title": title, "yt_link": yt_link, "yt_id": yt_id}
            )

        return jsonify({"batches": batches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/login", methods=["POST", "OPTIONS"])
def api_admin_login():
    if request.method == "OPTIONS":
        return _cors_preflight(["POST", "OPTIONS"])
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    if not data or data.get("password", "") != ADMIN_PASSWORD:
        return jsonify({"error": "Wrong password"}), 401

    token = make_token(ADMIN_PASSWORD)
    return jsonify({"token": token})


@app.route("/api/admin/data", methods=["GET", "OPTIONS"])
def api_admin_data():
    if request.method == "OPTIONS":
        return _cors_preflight(["GET", "OPTIONS"])

    token = request.headers.get("X-Admin-Token", "")
    if not valid_token(token):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        videos_col, vis_col = get_db()
        hidden_docs = list(vis_col.find({"hidden": True}))
        hidden_keys = {d["_id"] for d in hidden_docs}
        docs = list(videos_col.find({}, {"caption": 1, "yt_link": 1, "yt_id": 1}))

        batches = {}
        for doc in docs:
            caption = doc.get("caption", "")
            yt_link = doc.get("yt_link", "")
            yt_id = doc.get("yt_id", "")
            if not yt_link or not caption:
                continue
            p = parse_caption(caption)
            batch = p["batch"] or "Unknown Batch"
            topic = p["topic"] or "General"
            title = p["title"] or caption[:60]
            tkey = f"{batch}||{topic}"
            batches.setdefault(batch, {"hidden": batch in hidden_keys, "topics": {}})
            batches[batch]["topics"].setdefault(topic, {"hidden": tkey in hidden_keys, "lectures": []})
            batches[batch]["topics"][topic]["lectures"].append({"title": title, "yt_id": yt_id})

        return jsonify({"batches": batches})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/toggle", methods=["POST", "OPTIONS"])
def api_admin_toggle():
    if request.method == "OPTIONS":
        return _cors_preflight(["POST", "OPTIONS"])

    token = request.headers.get("X-Admin-Token", "")
    if not valid_token(token):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json(force=True)
        key = data.get("key")
        hidden = data.get("hidden")
        if not key:
            return jsonify({"error": "key required"}), 400
        _, vis_col = get_db()
        vis_col.update_one({"_id": key}, {"$set": {"hidden": hidden}}, upsert=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/ranaji")
def ranaji():
    return send_from_directory("public", "ranaji.html")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_static(path):
    if path and os.path.exists(os.path.join("public", path)):
        return send_from_directory("public", path)
    return send_from_directory("public", "index.html")


def _cors_preflight(methods):
    from flask import make_response
    resp = make_response("", 200)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = ", ".join(methods)
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    return resp


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
