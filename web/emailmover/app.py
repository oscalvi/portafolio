#!/usr/bin/env python3
"""
app.py — Flask backend for the EmailMover web app.

Design principles carried over from the desktop app:
  - Nothing is ever written to disk. Credentials and progress live only
    in memory, for the lifetime of one request or one background job.
  - A transfer can take minutes, so it runs in a background thread; the
    frontend polls /api/transfer/status/<job_id> for live progress,
    mirroring how the desktop app's ProgressWindow worked.
  - Jobs are identified by an opaque id, not tied to any stored user
    account - closing the browser tab and never returning simply means
    the job (and its credentials) are garbage collected once it ends.
"""

import os
import json
import threading
import time

from flask import Flask, jsonify, request, render_template

import imap_core
from job_manager import JobManager

app = Flask(__name__)
# Without this, Flask caches each compiled template in memory the first
# time it's read and never looks at the file again until the whole
# process restarts - so editing a .html file on disk (e.g. dropping in
# an updated template) would silently keep serving the old version even
# after a browser hard-refresh, until "Start EmailMover.bat" was closed
# and reopened. Auto-reloading avoids that trap.
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Generic job store/runner - see job_manager.py. Knows nothing about IMAP;
# imap_core.IMAPMigrationWorker is the polymorphic piece that plugs in.
job_manager = JobManager(ttl_seconds=30 * 60)

# Known IMAP settings (provider/host/port only - never a password, which
# stays true to "we never save your password") keyed by email address, so
# returning to a known account doesn't mean re-typing its server details.
USER_IMAP_INFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UserImapInfo.json")


def load_user_imap_info(email):
    try:
        with open(USER_IMAP_INFO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data.get(email)


@app.route("/api/user-imap-info", methods=["GET"])
def user_imap_info():
    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"ok": False, "error": "Missing 'email'"}), 400
    info = load_user_imap_info(email)
    if info is None:
        return jsonify({"ok": True, "found": False})
    return jsonify({"ok": True, "found": True, "info": info})


# --- DEV-ONLY: local test credentials, never shipped in the installer ---
# _local_test_secrets.json is NOT in installer.nsi's file list, so a real
# install of EmailMover never has this file and this endpoint always
# just returns "not found" there. It exists purely so we don't retype
# test passwords while developing - it must never hold real passwords,
# and this is the ONLY place in the whole app that ever reads a password
# back out of a file (everywhere else, "we never save your password"
# stays true).
DEV_SECRETS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_local_test_secrets.json")


@app.route("/api/dev-test-credentials", methods=["GET"])
def dev_test_credentials():
    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"ok": True, "found": False})
    try:
        with open(DEV_SECRETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"ok": True, "found": False})
    info = data.get(email)
    if info is None:
        return jsonify({"ok": True, "found": False})
    return jsonify({"ok": True, "found": True, "info": info})


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    """Closes EmailMover from the "Salir" link in the header. There's no
    supported cross-version way to ask Werkzeug's dev server to shut down
    gracefully, so this just exits the whole process right after the
    response goes out - fine for a single-user local tool."""
    def stop():
        time.sleep(0.3)
        os._exit(0)
    threading.Thread(target=stop, daemon=True).start()
    return jsonify({"ok": True})


def _account_from_request(data):
    """Build the {host, port, ssl, username, password} dict connect() wants,
    from the frontend's JSON payload for one account."""
    return {
        "host": data["host"],
        "port": int(data.get("port", 993)),
        "ssl": True,
        "username": data["username"],
        "password": data["password"],
    }


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/test-connection", methods=["POST"])
def test_connection():
    data = request.get_json(force=True)
    results = {}
    for side in ("source", "destination"):
        try:
            cfg = _account_from_request(data[side])
            conn = imap_core.connect(cfg)
            conn.logout()
            results[side] = {"ok": True}
        except Exception as e:
            results[side] = {"ok": False, "error": str(e)}
    overall_ok = results["source"]["ok"] and results["destination"]["ok"]
    return jsonify({"ok": overall_ok, "results": results})


@app.route("/api/folders", methods=["POST"])
def folders():
    data = request.get_json(force=True)
    try:
        cfg = _account_from_request(data["source"])
        conn = imap_core.connect(cfg)
        try:
            raw_folders = imap_core.list_folders(conn)
        finally:
            conn.logout()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    selectable = [name for flags, _delim, name in raw_folders if r"\Noselect" not in flags]
    delim = next((d for _f, d, _n in raw_folders if d), "/")
    tree = _build_tree(selectable, delim)
    return jsonify({"ok": True, "delimiter": delim, "tree": tree, "folders": selectable})


def _build_tree(names, delim):
    """Same nested-dict tree the desktop app's folder browser used, so the
    frontend can render an Explorer-style hierarchy."""
    tree = {}
    for full in names:
        parts = full.split(delim) if delim else [full]
        node = tree
        for i, part in enumerate(parts):
            node = node.setdefault(part, {"children": {}, "full": None})
            if i == len(parts) - 1:
                node["full"] = full
            node = node["children"]

    def to_list(subtree):
        out = []
        for name, info in sorted(subtree.items()):
            out.append({
                "name": name,
                "full": info["full"],
                "children": to_list(info["children"]),
            })
        return out

    return to_list(tree)


@app.route("/api/folder-counts", methods=["POST"])
def folder_counts():
    """Real, freshly-checked message counts AND a short list of the most
    recent messages for each folder on one account - used as independent
    proof after a transfer, by looking at the destination account
    directly rather than trusting the transfer job's own log."""
    data = request.get_json(force=True)
    try:
        cfg = _account_from_request(data["account"])
        folder_names = data["folders"]
        conn = imap_core.connect(cfg)
        counts = {}
        messages = {}
        try:
            for name in folder_names:
                counts[name] = imap_core.get_message_count(conn, name)
                messages[name] = imap_core.get_recent_messages(conn, name, limit=5)
        finally:
            conn.logout()
        return jsonify({"ok": True, "counts": counts, "messages": messages})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/transfer/start", methods=["POST"])
def start_transfer():
    data = request.get_json(force=True)
    dry_run = bool(data.get("dry_run", False))

    try:
        cfg = {
            "mode": data.get("mode", "copy"),
            "source": _account_from_request(data["source"]),
            "destination": _account_from_request(data["destination"]),
            "folders": data["folders"],  # [{"src":..,"dst":..}, ...]
        }
    except KeyError as e:
        return jsonify({"ok": False, "error": f"Missing field: {e}"}), 400

    if cfg["mode"] not in ("copy", "move"):
        return jsonify({"ok": False, "error": "mode must be 'copy' or 'move'"}), 400
    if not cfg["folders"]:
        return jsonify({"ok": False, "error": "No folders selected"}), 400

    job_id = job_manager.start(imap_core.IMAPMigrationWorker(cfg, dry_run))
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/transfer/status/<job_id>", methods=["GET"])
def transfer_status(job_id):
    since = int(request.args.get("since", 0))
    status = job_manager.status(job_id, since=since)
    if status is None:
        return jsonify({"ok": False, "error": "Unknown job_id (it may have expired)"}), 404
    return jsonify({"ok": True, **status})


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Frontend pages - both extend templates/base.html, so header, colors,
# buttons and footer stay uniform across the whole app; each page only
# supplies its own content/extra_style/extra_scripts blocks.
# ---------------------------------------------------------------------------

@app.route("/")
def serve_index():
    return render_template("index.html")


@app.route("/app.html")
def serve_app():
    return render_template("app.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
