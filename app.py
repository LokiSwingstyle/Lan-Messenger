import os
import sqlite3
from datetime import datetime, time
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename

APP_ROOT = Path(__file__).parent
DB_PATH = APP_ROOT / "vcorporate.db"
UPLOAD_DIR = APP_ROOT / "vcorporate_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "lan-messenger-secret"
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

online_users = {}
user_sid = {}


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT,
            message TEXT,
            file_name TEXT,
            file_path TEXT,
            created_at TEXT NOT NULL,
            kind TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def store_message(room, sender, kind, message=None, recipient=None, file_name=None, file_path=None):
    created_at = datetime.utcnow().isoformat()
    conn = db_conn()
    conn.execute(
        """
        INSERT INTO messages(room, sender, recipient, message, file_name, file_path, created_at, kind)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (room, sender, recipient, message, file_name, file_path, created_at, kind),
    )
    conn.commit()
    conn.close()
    return created_at


def todays_history(room, username):
    utc_today = datetime.utcnow().date()
    start = datetime.combine(utc_today, time(0, 0, 0)).isoformat()
    end = datetime.combine(utc_today, time(23, 0, 0)).isoformat()

    conn = db_conn()
    if room.startswith("dm:"):
        _, a, b = room.split(":", 2)
        rows = conn.execute(
            """
            SELECT * FROM messages
            WHERE room = ?
              AND created_at >= ?
              AND created_at <= ?
            ORDER BY id ASC
            """,
            (f"dm:{min(a,b)}:{max(a,b)}", start, end),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM messages
            WHERE room = ?
              AND created_at >= ?
              AND created_at <= ?
            ORDER BY id ASC
            """,
            (room, start, end),
        ).fetchall()
    conn.close()

    return [dict(r) for r in rows]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    username = request.form.get("username", "Anonymous").strip() or "Anonymous"
    room = request.form.get("room", "general")
    recipient = request.form.get("recipient")
    up = request.files.get("file")

    if not up:
        return jsonify({"error": "No file provided"}), 400

    safe_name = secure_filename(up.filename) or "file"
    unique_name = f"{uuid4().hex}_{safe_name}"
    file_path = UPLOAD_DIR / unique_name
    up.save(file_path)

    created_at = store_message(
        room=room,
        sender=username,
        kind="file",
        recipient=recipient,
        file_name=safe_name,
        file_path=unique_name,
    )

    payload = {
        "room": room,
        "sender": username,
        "recipient": recipient,
        "kind": "file",
        "file_name": safe_name,
        "file_url": f"/files/{unique_name}",
        "created_at": created_at,
    }

    if room == "broadcast":
        emit("new_message", payload, broadcast=True, namespace="/")
    elif room.startswith("dm:"):
        emit("new_message", payload, room=room, namespace="/")
    else:
        emit("new_message", payload, room=room, namespace="/")

    return jsonify(payload)


@app.route("/files/<path:filename>")
def serve_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@socketio.on("register")
def register_user(data):
    username = (data.get("username") or "Anonymous").strip() or "Anonymous"
    online_users[request.sid] = username
    user_sid[username] = request.sid
    join_room("general")
    emit("online_users", sorted(set(online_users.values())), broadcast=True)


@socketio.on("join_room")
def on_join(data):
    room = data.get("room", "general")
    username = data.get("username", "Anonymous")
    join_room(room)
    history = todays_history(room, username)
    emit("room_history", {"room": room, "messages": history})


@socketio.on("leave_room")
def on_leave(data):
    leave_room(data.get("room", "general"))


@socketio.on("typing")
def on_typing(data):
    emit(
        "typing",
        {"room": data.get("room"), "username": data.get("username")},
        room=data.get("room"),
        include_self=False,
    )


@socketio.on("send_message")
def send_message(data):
    sender = data.get("sender", "Anonymous")
    room = data.get("room", "general")
    message = data.get("message", "").strip()
    recipient = data.get("recipient")
    if not message:
        return

    if room.startswith("dm:"):
        users = room.split(":")
        room = f"dm:{min(users[1], users[2])}:{max(users[1], users[2])}"

    created_at = store_message(room=room, sender=sender, message=message, recipient=recipient, kind="text")
    payload = {
        "room": room,
        "sender": sender,
        "recipient": recipient,
        "message": message,
        "kind": "text",
        "created_at": created_at,
    }

    if room == "broadcast":
        emit("new_message", payload, broadcast=True)
    else:
        emit("new_message", payload, room=room)


@socketio.on("disconnect")
def on_disconnect():
    username = online_users.pop(request.sid, None)
    if username and user_sid.get(username) == request.sid:
        user_sid.pop(username, None)
    emit("online_users", sorted(set(online_users.values())), broadcast=True)


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000)
