from functools import wraps
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth
from flask import Flask, jsonify, request, send_from_directory

from agent import ChatAgent

# Initialize Firebase Admin SDK (uses ADC on Cloud Run automatically)
firebase_admin.initialize_app()

app = Flask(__name__)

# Initialize the personalized chat agent (Vertex AI + Memory Bank).
# Set AGENT_ENGINE_NAME env var to reuse an existing Agent Engine instance;
# otherwise a new one is created on startup.
chat_agent = ChatAgent()

# Path to the built React app (ui/dist)
UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"


def require_auth(f):
    """Decorator that verifies the Firebase ID token from the Authorization header."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split("Bearer ")[1]
        try:
            decoded_token = firebase_auth.verify_id_token(token)
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401

        request.user = decoded_token
        return f(*args, **kwargs)

    return decorated


@app.route("/api/welcome_message")
@require_auth
def welcome_message():
    email = request.user.get("email", "user")
    return jsonify({"message": f"Welcome, {email}!"})


# ------------------------------------------------------------------
# Chat endpoints
# ------------------------------------------------------------------


@app.route("/api/chat", methods=["POST"])
@require_auth
def chat():
    """Send a message and receive an AI response (with conversation memory)."""
    body = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    if not message:
        return jsonify({"error": "Message is required"}), 400

    user_id = request.user["uid"]
    user_email = request.user.get("email", "")

    try:
        reply = chat_agent.chat(user_id, message, user_display_name=user_email)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/history")
@require_auth
def chat_history():
    """Return the full conversation history for the authenticated user."""
    user_id = request.user["uid"]
    history = chat_agent.get_history(user_id)
    return jsonify({"history": history})


@app.route("/api/chat/clear", methods=["POST"])
@require_auth
def clear_chat():
    """Clear conversation history for the authenticated user."""
    user_id = request.user["uid"]
    chat_agent.clear_history(user_id)
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    if UI_DIST.exists():
        return send_from_directory(UI_DIST, "index.html")
    return "Hello, World!"


# Serve static assets (JS, CSS, etc.) from ui/dist
@app.route("/<path:path>")
def serve_static(path):
    if UI_DIST.exists():
        file_path = UI_DIST / path
        if file_path.is_file():
            return send_from_directory(UI_DIST, path)
        # SPA fallback: unknown paths serve index.html for client-side routing
        return send_from_directory(UI_DIST, "index.html")
    return "Not found", 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
