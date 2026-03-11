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
from datetime import datetime
import uuid
from prompt_similarity import (
    PROMPT_SIM_THRESHOLD,
    PROMPT_SIM_TOP_K,
    PROMPT_SIM_MIN_CHARS,
    PROMPT_SIM_NEAR_DUP_THRESHOLD,
    find_similar_for_state,
    upsert_prompt_embedding_for_record,
    remove_prompt_embedding,
)
from notes_store import list_notes, save_note, delete_note

app = Flask(__name__)
app.secret_key = KEYS["FLASK_SECRET_KEY"]
app.register_blueprint(auth_bp)

# If set, /examples will show only these annotation IDs (in this exact order).
# Leave empty to use automatic latest-complete sampling.
EXAMPLE_ANNOTATION_IDS = [
    "51147a23-93a1-4f92-9629-6e7e91ed497e",
    "c938d8c6-e82c-481e-afd5-0beac5ef935b",
    "adc1750a-538e-4c0a-907d-dc67c5baba08",
    "19592883-74f0-4f9d-bed5-a8dccc778510"
]

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
            return redirect(url_for("auth.login"))
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


def _safe_upsert_prompt_embedding(record):
    try:
        upsert_prompt_embedding_for_record(record)
    except Exception as e:
        print(f"⚠️ Prompt embedding upsert failed for {record.get('id')}: {e}")

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
        user=session.get("user"),
        current_annotation_id=session.get("editing_id", "")
    )


@app.route("/notes", methods=["GET", "POST"])
@login_required
def notes():
    user = session.get("user", {})
    username = (user.get("username") or "").strip()
    default_state = (user.get("state") or "").strip()

    info = None
    error = None
    draft_prompt = ""

    if request.method == "POST":
        action = (request.form.get("action") or "save").strip()

        if action == "save":
            draft_prompt = (request.form.get("prompt") or "").strip()
            note_state = (request.form.get("state") or default_state).strip()

            if not draft_prompt:
                error = "Please enter a prompt before saving."
            else:
                try:
                    save_note(username=username, prompt=draft_prompt, state=note_state)
                    info = "Prompt saved to your notes."
                    draft_prompt = ""
                except Exception as e:
                    error = f"Could not save note: {e}"

        elif action == "delete":
            note_id = (request.form.get("note_id") or "").strip()
            try:
                deleted = delete_note(username=username, note_id=note_id)
                info = "Note deleted." if deleted else "Note not found."
            except Exception as e:
                error = f"Could not delete note: {e}"

    try:
        saved_notes = list_notes(username=username)
    except Exception as e:
        saved_notes = []
        if not error:
            error = f"Could not load notes: {e}"

    return render_template(
        "notes.html",
        user=user,
        default_state=default_state,
        notes=saved_notes,
        info=info,
        error=error,
        draft_prompt=draft_prompt,
    )


@app.route("/check-prompt-similarity", methods=["POST"])
@login_required
def check_prompt_similarity():
    data = request.json or {}
    prompt = (data.get("prompt") or "").strip()
    state = (data.get("state") or "").strip()
    current_annotation_id = (data.get("current_annotation_id") or "").strip() or None

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400
    if not state:
        return jsonify({"error": "State is required"}), 400

    if len(prompt) < PROMPT_SIM_MIN_CHARS:
        return jsonify({
            "threshold": PROMPT_SIM_THRESHOLD,
            "count": 0,
            "matches": [],
            "message": f"Enter at least {PROMPT_SIM_MIN_CHARS} characters to check similarity."
        })

    try:
        matches = find_similar_for_state(
            prompt=prompt,
            state=state,
            threshold=PROMPT_SIM_THRESHOLD,
            top_k=PROMPT_SIM_TOP_K,
            exclude_annotation_id=current_annotation_id,
        )
    except Exception as e:
        return jsonify({"error": f"Similarity check failed: {e}"}), 500
        
    near_duplicate = any(m["similarity"] >= PROMPT_SIM_NEAR_DUP_THRESHOLD for m in matches)
    return jsonify({
        "threshold": PROMPT_SIM_THRESHOLD,
        "count": len(matches),
        "matches": matches,
        "near_duplicate": near_duplicate,
        "message": "Similar prompts found." if matches else "No similar prompts above threshold."
    })

@app.route("/promptreview")
@login_required
def prompt_review():
    user = session["user"]

    if user.get("role") != "annotator":
        return render_template(
            "review_list.html",
            records=[],
            review_counts={},
            clustered_records=[],
            info="IAA review is available only for annotators."
        )

    try:
        records = load_records_from_sheet()
        reviewed_ids = get_reviewed_annotation_ids_by_user(user["username"])
        review_counts = get_completed_review_counts_by_annotation(rows_per_reviewer=9)
    except Exception as e:
        return render_template(
            "review_list.html",
            records=[],
            review_counts={},
            clustered_records=[],
            error=f"Could not load review queue from Google Sheets: {e}"
        )

    reviewable = [
        r for r in records
        if r.get("state") == user.get("state")
        and r.get("region") == user.get("region")
        and r.get("annotator_name") != user.get("username")
        and r.get("id") not in reviewed_ids
    ]

    reviewable_sorted = sorted(
        reviewable,
        key=lambda r: (
            r.get("region", ""),
            r.get("state", ""),
            r.get("id", "")
        )
    )

    clustered_map = {}
    for r in reviewable_sorted:
        key = (r.get("region", "Unknown"), r.get("state", "Unknown"))
        clustered_map.setdefault(key, []).append(r)

    clustered_records = [
        {
            "region": key[0],
            "state": key[1],
            "records": grouped_records
        }
        for key, grouped_records in clustered_map.items()
    ]

    return render_template(
        "review_list.html",
        records=reviewable,
        review_counts=review_counts,
        clustered_records=clustered_records
    )


@app.route("/review/<annotation_id>")
@login_required
def review_annotation(annotation_id):
    user = session["user"]

    if user.get("role") != "annotator":
        abort(403)

    records = load_records_from_sheet()
    record = next((r for r in records if r.get("id") == annotation_id), None)

    if not record:
        abort(404)

    if (
        record.get("state") != user.get("state")
        or record.get("region") != user.get("region")
        or record.get("annotator_name") == user.get("username")
    ):
        abort(403)

    reviewed_ids = get_reviewed_annotation_ids_by_user(user["username"])
    if annotation_id in reviewed_ids:
        return redirect(url_for("prompt_review"))

    models = [
        ("gemini", "Model 1"),
        ("gpt", "Model 2"),
        ("llama", "Model 3"),
        ("deepseek", "Model 4"),
    ]

    return render_template(
        "review_annotation.html",
        record=record,
        models=models
    )


def _build_review_rows(form, user):
    annotation_id = form.get("annotation_id", "").strip()
    timestamp = datetime.utcnow().isoformat()
    needs_adjudication = form.get("needs_adjudication", "no")
    ground_truth_rating = form.get("ground_truth_rating", "unsure")

    rows = []
    for model in ["gemini", "gpt", "llama", "deepseek"]:
        for prompt_type in ["base", "identity"]:
            prefix = f"{model}_{prompt_type}"
            rows.append([
                str(uuid.uuid4()),
                annotation_id,
                user["username"],
                user.get("region", ""),
                user.get("state", ""),
                model,
                prompt_type,
                form.get(f"{prefix}_q0", "unsure"),
                form.get(f"{prefix}_q1", "unsure"),
                form.get(f"{prefix}_q2", "unsure"),
                form.get(f"{prefix}_q3", "medium"),
                "",
                needs_adjudication,
                timestamp,
            ])

    rows.append([
        str(uuid.uuid4()),
        annotation_id,
        user["username"],
        user.get("region", ""),
        user.get("state", ""),
        "ground_truth",
        "ground_truth",
        "",
        "",
        "",
        "",
        ground_truth_rating,
        needs_adjudication,
        timestamp,
    ])

    return rows


@app.route("/submit_review", methods=["POST"])
@login_required
def submit_review():
    user = session["user"]

    if user.get("role") != "annotator":
        abort(403)

    annotation_id = request.form.get("annotation_id", "").strip()
    if not annotation_id:
        abort(400)

    records = load_records_from_sheet()
    record = next((r for r in records if r.get("id") == annotation_id), None)

    if not record:
        abort(404)

    if (
        record.get("state") != user.get("state")
        or record.get("region") != user.get("region")
        or record.get("annotator_name") == user.get("username")
    ):
        abort(403)

    reviewed_ids = get_reviewed_annotation_ids_by_user(user["username"])
    if annotation_id in reviewed_ids:
        return redirect(url_for("prompt_review"))

    review_rows = _build_review_rows(request.form, user)
    append_review_rows(review_rows)

    return redirect(url_for("prompt_review"))


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
    def _has_text(value):
        return bool(str(value).strip()) if value is not None else False

    def _is_complete(record):
        prompts = record.get("prompts", {})
        if not _has_text(prompts.get("base")) or not _has_text(prompts.get("identity")):
            return False

        outputs = record.get("outputs", {})
        for model in ["gemini", "gpt", "llama", "deepseek"]:
            for kind in ["base", "identity"]:
                text = outputs.get(model, {}).get(kind, {}).get("text")
                if not _has_text(text):
                    return False

        return _has_text(record.get("ground_truth"))

    try:
        records = load_records_from_sheet()
    except Exception as e:
        return render_template(
            "examples.html",
            samples=[],
            error=f"Could not load examples from Google Sheets: {e}"
        )

    if EXAMPLE_ANNOTATION_IDS:
        records_by_id = {r.get("id"): r for r in records if r.get("id")}
        selected_records = [
            records_by_id[_id]
            for _id in EXAMPLE_ANNOTATION_IDS
            if _id in records_by_id
        ]
    else:
        complete_records = [r for r in records if _is_complete(r)]
        source_records = complete_records if complete_records else records
        selected_records = source_records[-5:]
        selected_records.reverse()

    samples = []
    for idx, r in enumerate(selected_records, start=1):
        samples.append({
            "label": f"Sample {idx} ({r.get('region', 'Unknown')} / {r.get('state', 'Unknown')})",
            "region": r.get("region", ""),
            "state": r.get("state", ""),
            "prompts": r.get("prompts", {}),
            "outputs": r.get("outputs", {}),
            "ground_truth": r.get("ground_truth", ""),
            "references": r.get("references", ""),
        })

    return render_template("examples.html", samples=samples)

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
            _safe_upsert_prompt_embedding(record)
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
        _safe_upsert_prompt_embedding(record)

    else:
        print("in newroww")
        write_jsonl(record)
        append_row(json_to_row(record))
        _safe_upsert_prompt_embedding(record)

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
    for deleted_id in delete_ids:
        remove_prompt_embedding(deleted_id)

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
        review_counts = get_completed_review_counts_by_annotation(rows_per_reviewer=9)
        print("REVIEW COUNTS" , review_counts)
    except Exception as e:
        return render_template(
            "load_annotation.html",
            error=f"Could not load annotations from Google Sheets: {e}",
            user_records=[],
            review_counts={}
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
        load_mode = request.form.get("load_mode", "edit")

        if not annotation_id:
            return render_template(
                "load_annotation.html",
                error="Please enter a valid ID",
                user_records=user_records,
                review_counts=review_counts
            )

        for record in records:
            if record["id"] == annotation_id:
                if load_mode == "view":
                    return render_template(
                        "review.html",
                        record=record,
                        view_only=True
                    )

                if review_counts.get(annotation_id, 0) >= 1:
                    return render_template(
                        "load_annotation.html",
                        error="This annotation has already been reviewed and can no longer be edited.",
                        user_records=user_records,
                        review_counts=review_counts
                    )

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
            user_records=user_records,
            review_counts=review_counts
        )

    return render_template(
        "load_annotation.html",
        user_records=user_records,
        review_counts=review_counts
    )

if __name__ == "__main__":
    app.run(debug=True)
