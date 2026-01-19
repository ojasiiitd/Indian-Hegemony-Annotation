# app.py
from flask import Flask, render_template, request, redirect, jsonify, url_for, abort
from storage import *
from sheets import *
from flask import session
import json
from config import *
from llm import *
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = KEYS["FLASK_SECRET_KEY"]

@app.before_request
def validate_session():
    try:
        _ = session.get("user")
    except Exception:
        session.clear()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = session.get("user")
        if not user or user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

@app.route("/", methods=["GET", "POST"])
@login_required
def annotate():
    if request.method == "POST":
        record = build_record(request.form)

        # 🔑 store draft
        session["draft_record"] = record

        return render_template(
            "review.html",
            record=record
        )

    # GET: render form, possibly pre-filled
    draft = session.get("draft_record")
    return render_template(
        "annotate.html",
        region_state_map=REGION_STATE_MAP,
        draft=draft
    )

@app.route("/freshannotate", methods=["GET", "POST"])
@login_required
def freshannotate():
    # Retrieve and discard draft
    session.pop("draft_record", None)
    return redirect("/")


@app.route("/confirm", methods=["POST"])
@login_required
def confirm():
    # Retrieve and discard draft in one step
    record = session.pop("draft_record", None)

    # Fallback safety (in case someone POSTs directly)
    if record is None:
        record = json.loads(request.form["record"])

    # 1. Write JSONL
    write_jsonl(record)

    # 2. Append to Google Sheets
    try:
        append_row(json_to_row(record))
    except Exception as e:
        print("Sheets write failed:", e)

    return redirect("/")

@app.route("/records")
@admin_required
def records():
    records = load_records()
    # show newest first
    records.reverse()
    return render_template("records.html", records=records)

@app.route("/admin")
@admin_required
def admin():
    records = load_records()
    return render_template("admin.html", records=records)


@app.route("/admin/delete", methods=["POST"])
@admin_required
def admin_delete():
    print("💀 admin_delete called")
    delete_ids = request.form.getlist("delete_ids")

    # if not delete_ids:
    #     return redirect(url_for("admin"))

    records = load_records()

    # Filter out deleted records
    remaining = [r for r in records if r["id"] not in delete_ids]

    # Rewrite JSONL
    rewrite_jsonl(remaining)

    clear_sheet_data()

    # Rebuild Google Sheet
    try:
        rebuild_sheet_from_records(remaining)
    except Exception as e:
        print("Sheet rebuild failed:", e)

    return redirect(url_for("admin"))


@app.route("/generate/gemini", methods=["POST"])
def generate_gemini():
    print("😋 GEMINI called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_gemini_output(prompt)})


@app.route("/generate/gpt", methods=["POST"])
def generate_gpt():
    print("😋 Chat  GPT called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_gpt_output(prompt)})

@app.route("/generate/llama", methods=["POST"])
def generate_llama():
    print("😋 Llama called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_llama_output(prompt)})

@app.route("/generate/deepseek", methods=["POST"])
def generate_deepseek():
    print("😋 Deepseek called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_deepseek_output(prompt)})

@app.route("/references")
def references():
    return render_template("references.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # ---- ADMIN LOGIN ----
        if (
            username == KEYS["ADMIN_USERNAME"] and
            check_password_hash(KEYS["ADMIN_PASSWORD_HASH"], password)
        ):
            session["user"] = {
                "username": username,
                "role": "admin"
            }
            return redirect(url_for("annotate"))

        # ---- ANNOTATOR LOGIN ----
        if (
            username == KEYS["ANNOTATOR_USERNAME"] and
            check_password_hash(KEYS["ANNOTATOR_PASSWORD_HASH"], password)
        ):
            session["user"] = {
                "username": username,
                "role": "annotator"
            }
            return redirect(url_for("annotate"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)