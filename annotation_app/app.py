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
from auth import auth_bp
from draft_store import *

app = Flask(__name__)
app.secret_key = KEYS["FLASK_SECRET_KEY"]
app.register_blueprint(auth_bp)

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

        draft_id = save_draft(record)
        session["draft_id"] = draft_id

        return render_template("review.html", record=record)

    draft_id = session.get("draft_id")
    draft = load_draft(draft_id) if draft_id else None

    return render_template(
        "annotate.html",
        region_state_map=REGION_STATE_MAP,
        draft=draft,
        user=session.get("user")
    )

@app.route("/promptreview")
@login_required
def prompt_review():
    return "Hello"


@app.route("/freshannotate")
@login_required
def freshannotate():
    draft_id = session.pop("draft_id", None)
    session.pop("editing_id", None)
    if draft_id:
        delete_draft(draft_id)
    return redirect("/")

@app.route("/examples")
def examples():
    return render_template("examples.html")

@app.route("/confirm", methods=["POST"])
@login_required
def confirm():

    draft_id = session.pop("draft_id", None)
    editing_id = session.pop("editing_id", None)

    if not draft_id:
        abort(400)

    record = load_draft(draft_id)
    delete_draft(draft_id)

    if editing_id:
        print("in editinggg")

        # Update JSONL
        records = load_records()
        record_exists = any(r["id"] == editing_id for r in records)

        # If stale editing_id leaked in session, treat this submission as a new row.
        if not record_exists:
            print("stale editing_id; falling back to new row")
            write_jsonl(record)
            append_row(json_to_row(record))
            return redirect("/")

        record["id"] = editing_id
        updated_records = []

        for r in records:
            if r["id"] == editing_id:
                updated_records.append(record)
            else:
                updated_records.append(r)

        rewrite_jsonl(updated_records)

        # 🔥 Update single row in Sheets
        update_row_by_id(editing_id, json_to_row(record))

    else:
        print("in newroww")
        write_jsonl(record)
        append_row(json_to_row(record))

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
@login_required
def generate_gemini():
    print("😋 GEMINI called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_gemini_output(prompt)})


@app.route("/generate/gpt", methods=["POST"])
@login_required
def generate_gpt():
    print("😋 Chat  GPT called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_gpt_output(prompt)})

@app.route("/generate/llama", methods=["POST"]) # actually gpt oss 120b
@login_required
def generate_llama():
    print("😋 GPT-OSS called")
    data = request.json
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    return jsonify({"text": generate_llama_output(prompt)})

@app.route("/generate/deepseek", methods=["POST"])
@login_required
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

@app.route("/load-annotation", methods=["GET", "POST"])
@login_required
def load_annotation():

    user = session["user"]["username"]
    try:
        records = load_records_from_sheet()
    except Exception as e:
        return render_template(
            "load_annotation.html",
            error=f"Could not load annotations from Google Sheets: {e}",
            user_records=[]
        )

    # 🔒 Only current annotator's records (admins see all)
    if session["user"]["role"] == "admin":
        user_records = records
    else:
        user_records = [
            r for r in records
            if r["annotator_name"] == user
        ]

    if request.method == "POST":
        annotation_id = request.form.get("annotation_id", "").strip()

        if not annotation_id:
            return render_template(
                "load_annotation.html",
                error="Please enter a valid ID",
                user_records=user_records
            )

        for record in records:
            if record["id"] == annotation_id:

                # # 🔐 Security check
                # if (
                #     session["user"]["role"] != "admin"
                #     and record["annotator_name"] != user
                # ):
                #     return render_template(
                #         "load_annotation.html",
                #         error="You cannot edit someone else's annotation.",
                #         user_records=user_records
                #     )

                draft_id = save_draft(record)
                session["draft_id"] = draft_id
                session["editing_id"] = annotation_id

                return redirect(url_for("annotate"))

        return render_template(
            "load_annotation.html",
            error="Annotation ID not found",
            user_records=user_records
        )

    return render_template(
        "load_annotation.html",
        user_records=user_records
    )

if __name__ == "__main__":
    app.run(debug=True)
