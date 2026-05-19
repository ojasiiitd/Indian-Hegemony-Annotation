# app.py
from flask import Flask, render_template, request, redirect, jsonify, url_for, abort, Response
from storage import *
from sheets import *
from flask import session
import json
from config import *
from llm import *
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from auth import auth_bp, load_annotators
from draft_store import *
from datetime import datetime
import uuid
from collections import Counter, defaultdict
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
from iaa_store import (
    IAA_REVIEW_COLUMNS,
    count_completed_iaa_reviews_by_annotation,
    fetch_iaa_review,
    initialize_iaa_storage,
    list_completed_iaa_annotation_ids_for_reviewer,
    list_iaa_reviews_for_export,
    save_iaa_review,
)
import csv
import io
import random

app = Flask(__name__)
app.secret_key = KEYS["FLASK_SECRET_KEY"]
app.register_blueprint(auth_bp)
initialize_iaa_storage()

# If set, /examples will show only these annotation IDs (in this exact order).
# Leave empty to use automatic latest-complete sampling.
EXAMPLE_ANNOTATION_IDS = [
    "582abe5e-c80a-4306-9086-00ebf7b660d4",
    "69782176-23f7-488d-a10a-670f30f26622",
    "0a277487-7037-49f9-96b4-ffc7ae804f32",
    "d1cddafd-aed5-4a8f-981c-37264dbd0bca",
    "4d17f079-083a-40a6-bdee-010af3943430",
    "5a83933e-74fb-422b-ab62-ec1c4e0bb8c0",
    "51147a23-93a1-4f92-9629-6e7e91ed497e",
]


def _normalize_username(value):
    return " ".join(str(value or "").split()).casefold()


ONBOARDED_ANNOTATOR_SET = {
    _normalize_username(username)
    for username in ONBOARDED_ANNOTATOR_USERNAMES
    if _normalize_username(username)
}

@app.before_request
def validate_session():
    try:
        _ = session.get("user")
    except Exception:
        session.clear()


@app.context_processor
def inject_template_flags():
    user = session.get("user") or {}
    username = user.get("username")
    return {
        "show_timesheet_link": _normalize_username(username) in ONBOARDED_ANNOTATOR_SET
    }

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


def _preserve_record_fields(record, existing_record, field_names):
    if not existing_record:
        return record

    for field_name in field_names:
        if field_name not in record or record.get(field_name, "") == "":
            record[field_name] = existing_record.get(field_name, "")

    return record


def _load_annotation_record(annotation_id):
    try:
        records = load_records_from_sheet()
        data_source = "Google Sheets"
        load_error = None
    except Exception as e:
        records = load_records()
        data_source = "Local JSONL (fallback)"
        load_error = f"Could not load records from Google Sheets: {e}. Showing local data."

    record = next((r for r in records if r.get("id") == annotation_id), None)
    return record, data_source, load_error


def _sync_local_record_fields(record_id, field_updates):
    records = load_records()
    updated = False

    for record in records:
        if record.get("id") != record_id:
            continue
        record.update(field_updates)
        updated = True
        break

    if updated:
        rewrite_jsonl(records)

    return updated


def _is_checked_value(value):
    return str(value or "").strip().casefold() in {"yes", "true", "1", "validated", "accepted"}


def _is_restructure_value(value):
    return str(value or "").strip().casefold().replace(" ", "_") in {
        "needs_restructuring",
        "needs-restructuring",
        "restructure",
        "needsrestructuring",
    }


def _normalize_acceptance_choice(value):
    clean_value = str(value or "").strip()
    if _is_checked_value(clean_value):
        return "yes"
    if _is_restructure_value(clean_value):
        return "needs_restructuring"
    if clean_value.casefold() == "no":
        return "no"
    return ""


def _annotator_addressed_status(value):
    clean_value = str(value or "").strip().casefold()
    if clean_value == "yes":
        return "yes"
    if clean_value == "no":
        return "no"
    return "pending"


def _acceptance_status(value):
    clean_value = str(value or "").strip()
    if not clean_value:
        return "pending"
    if _is_checked_value(clean_value):
        return "accepted"
    if _is_restructure_value(clean_value):
        return "needs_restructuring"
    return "rejected"


def _is_iaa_approved_record(record):
    clean_value = str((record or {}).get("isAccept") or "").strip().casefold().replace(" ", "_")
    return clean_value in {"yes", "accepted", "approved", "true", "1"}


def _parse_iaa_score(form, field_name, default=0):
    raw_value = str(form.get(field_name, default)).strip()
    if raw_value in {"0", "1", "2", "3", "4", "5"}:
        return int(raw_value)
    return int(default)


def _optional_text(form, field_name):
    value = str(form.get(field_name, "") or "").strip()
    return value or None


def _parse_optional_iaa_score(form, field_name):
    raw_value = str(form.get(field_name, "") or "").strip()
    if raw_value in {"0", "1", "2", "3", "4", "5"}:
        return int(raw_value)
    return None


def _iaa_review_to_form_values(review):
    if not review:
        return {}

    field_map = {
        "prompt_q0": "prompt_q1_clarity_format",
        "prompt_q1": "prompt_q2_cultural_context",
        "prompt_q2": "prompt_q3_identity_relevance",
        "ground_truth_rating": "groundtruth_q1_corrective_quality",
        "optional_comment": "optional_comment",
        "reviewer_confidence": "reviewer_confidence",
    }

    for model in ["gemini", "gpt", "llama", "deepseek"]:
        for prompt_type in ["base", "identity"]:
            prefix = f"{model}_{prompt_type}"
            db_prefix = f"{model}_{prompt_type}"
            field_map[f"{prefix}_q2"] = f"{db_prefix}_output_q1_hegemony_presence"
            field_map[f"{prefix}_q3"] = f"{db_prefix}_output_q2_axes_match"
            field_map[f"{prefix}_q4"] = f"{db_prefix}_output_q3_reasoning_quality"
            field_map[f"{prefix}_q5"] = f"{db_prefix}_output_q4_hegemony_severity"

    form_values = {}
    for form_name, db_name in field_map.items():
        value = review.get(db_name)
        form_values[form_name] = "" if value is None else str(value)
    return form_values


def _build_iaa_review_payload(form, user, record):
    payload = {
        "annotation_id": str(record.get("id") or "").strip(),
        "reviewer_name": str(user.get("username") or "").strip(),
        "reviewer_state": str(user.get("state") or "").strip(),
        "annotation_creator": str(record.get("annotator_name") or "").strip(),
        "review_timestamp": datetime.utcnow().isoformat(),
        "editable": 0,
        "completed": 1,
        "prompt_q1_clarity_format": _parse_iaa_score(form, "prompt_q0"),
        "prompt_q2_cultural_context": _parse_iaa_score(form, "prompt_q1"),
        "prompt_q3_identity_relevance": _parse_iaa_score(form, "prompt_q2"),
        "groundtruth_q1_corrective_quality": _parse_iaa_score(form, "ground_truth_rating"),
        "optional_comment": _optional_text(form, "optional_comment"),
        "reviewer_confidence": _parse_optional_iaa_score(form, "reviewer_confidence"),
        "admin_notes": None,
    }

    for model in ["gemini", "gpt", "llama", "deepseek"]:
        for prompt_type in ["base", "identity"]:
            prefix = f"{model}_{prompt_type}"
            db_prefix = f"{model}_{prompt_type}"
            payload[f"{db_prefix}_output_q1_hegemony_presence"] = _parse_iaa_score(form, f"{prefix}_q2")
            payload[f"{db_prefix}_output_q2_axes_match"] = _parse_iaa_score(form, f"{prefix}_q3")
            payload[f"{db_prefix}_output_q3_reasoning_quality"] = _parse_iaa_score(form, f"{prefix}_q4")
            payload[f"{db_prefix}_output_q4_hegemony_severity"] = _parse_iaa_score(form, f"{prefix}_q5")

    return payload


def _persist_annotation_record(record, editing_id=None):
    """
    Persist annotation exactly like confirm flow.
    Returns: (saved_annotation_id, mode) where mode is 'created' or 'updated'.
    """
    if editing_id:
        records = load_records()
        record_exists = any(r["id"] == editing_id for r in records)

        # If stale editing_id leaked in session, fall back to creating a new row.
        if not record_exists:
            write_jsonl(record)
            append_row(json_to_row(record))
            _safe_upsert_prompt_embedding(record)
            return record["id"], "created"

        existing_record = next((r for r in records if r["id"] == editing_id), None)
        record = _preserve_record_fields(
            record,
            existing_record,
            ["expert_reviews", "isAccept", "annotator_addressed"],
        )
        record["id"] = editing_id
        updated_records = []
        for r in records:
            if r["id"] == editing_id:
                updated_records.append(record)
            else:
                updated_records.append(r)

        rewrite_jsonl(updated_records)
        update_row_by_id(editing_id, json_to_row(record))
        _safe_upsert_prompt_embedding(record)
        return editing_id, "updated"

    write_jsonl(record)
    append_row(json_to_row(record))
    _safe_upsert_prompt_embedding(record)
    return record["id"], "created"


def _has_text(value):
    return bool(str(value).strip()) if value is not None else False


def _parse_record_datetime(record):
    raw_ts = str(record.get("timestamp") or record.get("created_at") or "").strip()
    if not raw_ts:
        return None

    try:
        return datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    except ValueError:
        if len(raw_ts) >= 10 and raw_ts[4] == "-" and raw_ts[7] == "-":
            try:
                return datetime.fromisoformat(f"{raw_ts[:10]}T00:00:00")
            except ValueError:
                return None
        return None


def _record_day(record):
    parsed_dt = _parse_record_datetime(record)
    return parsed_dt.date().isoformat() if parsed_dt else ""


def _is_annotation_completed(record):
    prompts = record.get("prompts") or {}
    if not _has_text(prompts.get("base")) or not _has_text(prompts.get("identity")):
        return False

    if not _has_text(record.get("ground_truth")):
        return False

    outputs = record.get("outputs") or {}
    for model in ["gemini", "gpt", "llama", "deepseek"]:
        for kind in ["base", "identity"]:
            text = ((outputs.get(model) or {}).get(kind) or {}).get("text")
            if not _has_text(text):
                return False

    return True

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


@app.route("/save-annotation-draft", methods=["POST"])
@login_required
def save_annotation_draft():
    try:
        record = build_record(request.form)
        editing_id = session.get("editing_id")
        annotation_id, mode = _persist_annotation_record(record, editing_id=editing_id)
        session["editing_id"] = annotation_id

        return jsonify({
            "ok": True,
            "annotation_id": annotation_id,
            "mode": mode,
            "saved_at": datetime.utcnow().isoformat(),
            "message": "Annotation saved."
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Could not save annotation: {e}"
        }), 500


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
    page_info = (request.args.get("info") or "").strip()

    if user.get("role") not in {"annotator", "admin"}:
        return render_template(
            "review_list.html",
            records=[],
            review_counts={},
            clustered_records=[],
            info="IAA review is available only for annotators and admins."
        )

    try:
        records = load_records_from_sheet()
        reviewed_ids = list_completed_iaa_annotation_ids_for_reviewer(user["username"])
        review_counts = count_completed_iaa_reviews_by_annotation()
    except Exception as e:
        return render_template(
            "review_list.html",
            records=[],
            review_counts={},
            clustered_records=[],
            error=f"Could not load IAA review queue: {e}"
        )

    if user.get("role") == "admin":
        reviewable = [
            r for r in records
            if _is_iaa_approved_record(r)
            and r.get("annotator_name") != user.get("username")
            and r.get("id") not in reviewed_ids
        ]
    else:
        reviewable = [
            r for r in records
            if _is_iaa_approved_record(r)
            and r.get("state") == user.get("state")
            and r.get("annotator_name") != user.get("username")
            and r.get("id") not in reviewed_ids
        ]

    random.shuffle(reviewable)

    clustered_map = {}
    for r in reviewable:
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
        clustered_records=clustered_records,
        info=page_info,
    )


@app.route("/review/<annotation_id>")
@login_required
def review_annotation(annotation_id):
    user = session["user"]

    if user.get("role") not in {"annotator", "admin"}:
        abort(403)

    records = load_records_from_sheet()
    record = next((r for r in records if r.get("id") == annotation_id), None)

    if not record:
        abort(404)

    if not _is_iaa_approved_record(record):
        return redirect(url_for("prompt_review", info="Only approved annotations are eligible for IAA review."))

    if user.get("role") != "admin" and (
        record.get("state") != user.get("state")
        or record.get("annotator_name") == user.get("username")
    ):
        abort(403)

    if user.get("role") == "admin" and record.get("annotator_name") == user.get("username"):
        abort(403)

    existing_review = fetch_iaa_review(annotation_id, user["username"])
    if existing_review and existing_review.get("completed") and not existing_review.get("editable"):
        return redirect(url_for("prompt_review", info="You have already submitted an IAA review for this annotation."))

    models = [
        ("gemini", "Model 1"),
        ("gpt", "Model 2"),
        ("llama", "Model 3"),
        ("deepseek", "Model 4"),
    ]

    return render_template(
        "review_annotation.html",
        record=record,
        models=models,
        existing_review=_iaa_review_to_form_values(existing_review),
    )


@app.route("/submit_review", methods=["POST"])
@login_required
def submit_review():
    user = session["user"]

    if user.get("role") not in {"annotator", "admin"}:
        abort(403)

    annotation_id = request.form.get("annotation_id", "").strip()
    if not annotation_id:
        abort(400)

    records = load_records_from_sheet()
    record = next((r for r in records if r.get("id") == annotation_id), None)

    if not record:
        abort(404)

    if not _is_iaa_approved_record(record):
        return redirect(url_for("prompt_review", info="Only approved annotations are eligible for IAA review."))

    if user.get("role") != "admin" and (
        record.get("state") != user.get("state")
        or record.get("annotator_name") == user.get("username")
    ):
        abort(403)

    if user.get("role") == "admin" and record.get("annotator_name") == user.get("username"):
        abort(403)

    try:
        save_iaa_review(_build_iaa_review_payload(request.form, user, record))
    except PermissionError:
        return redirect(url_for("prompt_review", info="This IAA review is locked and can no longer be edited."))

    return redirect(url_for("prompt_review", info="IAA review submitted."))


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
            "expert_reviews": r.get("expert_reviews", ""),
            "isAccept": r.get("isAccept", ""),
            "annotator_addressed": r.get("annotator_addressed", ""),
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
    saved_id, mode = _persist_annotation_record(record, editing_id=editing_id)
    print(f"confirm persisted annotation {saved_id} ({mode})")

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
    user = session.get("user")
    data_source = "Google Sheets"
    error = None

    try:
        records = load_records_from_sheet()
    except Exception as e:
        records = load_records()
        data_source = "Local JSONL (fallback)"
        error = f"Could not load records from Google Sheets: {e}. Showing local data."

    try:
        annotators = load_annotators()
    except Exception as e:
        annotators = []
        if not error:
            error = f"Could not load registered annotators: {e}"

    annotation_count_by_annotator = Counter(
        (r.get("annotator_name") or "").strip() for r in records if (r.get("annotator_name") or "").strip()
    )

    annotator_stats = []
    seen_usernames = set()
    for a in annotators:
        username = (a.get("username") or "").strip()
        if not username:
            continue
        seen_usernames.add(username)
        annotator_stats.append({
            "username": username,
            "state": (a.get("state") or "Unknown").strip() or "Unknown",
            "region": (a.get("region") or "Unknown").strip() or "Unknown",
            "annotation_count": annotation_count_by_annotator.get(username, 0),
        })

    # Include annotations from usernames not present in annotators.json
    for username, count in annotation_count_by_annotator.items():
        if username not in seen_usernames:
            annotator_stats.append({
                "username": username,
                "state": "Unknown",
                "region": "Unknown",
                "annotation_count": count,
            })

    annotator_stats.sort(key=lambda x: (-x["annotation_count"], x["username"].lower()))

    registered_by_state = Counter(
        (a.get("state") or "Unknown").strip() or "Unknown" for a in annotators
    )

    state_annotation_count = Counter()
    reviewed_state_annotation_count = Counter()
    approved_state_annotation_count = Counter()
    state_active_annotators = defaultdict(set)
    for r in records:
        state = (r.get("state") or "Unknown").strip() or "Unknown"
        username = (r.get("annotator_name") or "").strip()
        state_annotation_count[state] += 1
        acceptance_status = _acceptance_status(r.get("isAccept"))
        if acceptance_status != "pending":
            reviewed_state_annotation_count[state] += 1
        if acceptance_status in ("accepted", "needs_restructuring"):
            approved_state_annotation_count[state] += 1
        if username:
            state_active_annotators[state].add(username)

    all_states = set(registered_by_state.keys()) | set(state_annotation_count.keys())
    state_stats = []
    for state in sorted(all_states):
        state_stats.append({
            "state": state,
            "registered_annotators": registered_by_state.get(state, 0),
            "active_annotators": len(state_active_annotators.get(state, set())),
            "annotation_count": state_annotation_count.get(state, 0),
        })

    state_stats.sort(key=lambda x: (-x["annotation_count"], x["state"].lower()))

    reviewed_state_stats = [
        {"state": state, "annotation_count": count}
        for state, count in reviewed_state_annotation_count.items()
    ]
    reviewed_state_stats.sort(key=lambda x: (-x["annotation_count"], x["state"].lower()))

    approved_state_stats = [
        {"state": state, "annotation_count": count}
        for state, count in approved_state_annotation_count.items()
    ]
    approved_state_stats.sort(key=lambda x: (-x["annotation_count"], x["state"].lower()))

    daily_annotation_count = Counter()
    for r in records:
        day_key = _record_day(r)
        if day_key:
            daily_annotation_count[day_key] += 1

    running_total = 0
    daily_progress = []
    for day in sorted(daily_annotation_count.keys()):
        running_total += daily_annotation_count[day]
        daily_progress.append({
            "date": day,
            "count": daily_annotation_count[day],
            "cumulative": running_total,
        })

    totals = {
        "registered_annotators": len([a for a in annotators if (a.get("username") or "").strip()]),
        "active_annotators": len([s for s in annotator_stats if s["annotation_count"] > 0]),
        "total_annotations": len(records),
        "states_covered": len(all_states),
    }

    query_state = (request.args.get("state") or "").strip()
    query_annotator = (request.args.get("annotator") or "").strip()
    query_validation = (request.args.get("validation") or "").strip()
    query_drafts = (request.args.get("drafts") or "hide").strip() or "hide"
    query_sort = (request.args.get("sort") or "date_desc").strip() or "date_desc"

    filtered_records = []
    for r in records:
        if query_state and (r.get("state") or "").strip() != query_state:
            continue
        if query_annotator:
            annotator_name = (r.get("annotator_name") or "").strip().lower()
            if query_annotator.lower() not in annotator_name:
                continue
        is_completed = _is_annotation_completed(r)
        if query_drafts == "hide" and not is_completed:
            continue
        acceptance_status = _acceptance_status(r.get("isAccept"))
        is_validated = acceptance_status != "pending"
        if query_validation == "validated" and not is_validated:
            continue
        if query_validation == "non_validated" and is_validated:
            continue
        parsed_timestamp = _parse_record_datetime(r)
        filtered_records.append({
            **r,
            "_is_completed": is_completed,
            "_is_onboarded": _normalize_username(r.get("annotator_name")) in ONBOARDED_ANNOTATOR_SET,
            "_acceptance_status": acceptance_status,
            "_annotator_addressed_status": _annotator_addressed_status(r.get("annotator_addressed")),
            "_is_validated": is_validated,
            "_parsed_timestamp": parsed_timestamp,
            "_sort_timestamp": parsed_timestamp.timestamp() if parsed_timestamp else float("-inf"),
        })

    sort_options = {
        "date_desc": {
            "label": "Newest First",
            "key": lambda r: (
                r.get("_sort_timestamp", float("-inf")),
                (r.get("annotator_name") or "").strip().casefold(),
            ),
            "reverse": True,
        },
        "date_asc": {
            "label": "Oldest First",
            "key": lambda r: (
                r.get("_sort_timestamp", float("-inf")),
                (r.get("annotator_name") or "").strip().casefold(),
            ),
            "reverse": False,
        },
        "name_asc": {
            "label": "Annotator Name (A-Z)",
            "key": lambda r: (
                (r.get("annotator_name") or "").strip().casefold(),
                (r.get("state") or "").strip().casefold(),
                -r.get("_sort_timestamp", float("-inf")),
            ),
            "reverse": False,
        },
        "state_asc": {
            "label": "State (A-Z)",
            "key": lambda r: (
                (r.get("state") or "").strip().casefold(),
                (r.get("annotator_name") or "").strip().casefold(),
                -r.get("_sort_timestamp", float("-inf")),
            ),
            "reverse": False,
        },
        "validation_desc": {
            "label": "Validation Status",
            "key": lambda r: (
                0 if r.get("_is_validated") else 1,
                (r.get("_acceptance_status") or "").strip(),
                -r.get("_sort_timestamp", float("-inf")),
            ),
            "reverse": False,
        },
    }
    selected_sort = sort_options.get(query_sort, sort_options["date_desc"])
    if query_sort not in sort_options:
        query_sort = "date_desc"
    filtered_records.sort(key=selected_sort["key"], reverse=selected_sort["reverse"])

    available_states = sorted({
        (r.get("state") or "").strip()
        for r in records
        if (r.get("state") or "").strip()
    })

    return render_template(
        "admin.html",
        user=user,
        region_state_map=REGION_STATE_MAP,
        records=records,
        annotator_stats=annotator_stats,
        state_stats=state_stats,
        reviewed_state_stats=reviewed_state_stats,
        approved_state_stats=approved_state_stats,
        daily_progress=daily_progress,
        filtered_records=filtered_records,
        available_states=available_states,
        query_state=query_state,
        query_annotator=query_annotator,
        query_validation=query_validation,
        query_drafts=query_drafts,
        query_sort=query_sort,
        sort_options={key: option["label"] for key, option in sort_options.items()},
        totals=totals,
        data_source=data_source,
        error=error,
    )


@app.route("/admin/iaa-reviews.csv")
@admin_required
def export_iaa_reviews_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["review_id"] + list(IAA_REVIEW_COLUMNS))
    writer.writeheader()
    for row in list_iaa_reviews_for_export():
        writer.writerow(row)

    csv_data = output.getvalue()
    output.close()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=iaa_reviews.csv"},
    )


@app.route("/admin/annotations.csv")
@admin_required
def export_annotations_csv():
    try:
        records = load_records_from_sheet()
    except Exception as e:
        abort(500, description=f"Could not export annotations: {e}")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    for record in records:
        writer.writerow(json_to_row(record))

    csv_data = output.getvalue()
    output.close()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=annotations_sheet1.csv"},
    )


@app.route("/admin/load/<annotation_id>", methods=["GET", "POST"])
@admin_required
def admin_load_annotation(annotation_id):
    record, data_source, load_error = _load_annotation_record(annotation_id)
    if not record:
        abort(404)

    admin_review_error = load_error

    if request.method == "POST":
        selected_acceptance = _normalize_acceptance_choice(request.form.get("isAccept"))
        updated_record = {
            **record,
            "expert_reviews": (request.form.get("expert_reviews") or "").strip(),
            "isAccept": selected_acceptance,
            # A fresh restructure request should require the annotator to
            # acknowledge/address the latest reviewer feedback again.
            "annotator_addressed": "",
        }

        try:
            update_row_by_id(annotation_id, json_to_row(updated_record))
            _sync_local_record_fields(
                annotation_id,
                {
                    "expert_reviews": updated_record.get("expert_reviews", ""),
                    "isAccept": updated_record.get("isAccept", ""),
                    "annotator_addressed": updated_record.get("annotator_addressed", ""),
                },
            )
            return redirect(url_for("admin_load_annotation", annotation_id=annotation_id, saved="1"))
        except Exception as e:
            admin_review_error = f"Could not save expert review: {e}"
            record = updated_record

    return render_template(
        "review.html",
        record=record,
        view_only=True,
        back_url=url_for("admin"),
        admin_review=True,
        admin_review_saved=request.args.get("saved") == "1",
        admin_review_error=admin_review_error,
        admin_acceptance_value=_normalize_acceptance_choice(record.get("isAccept")),
        annotator_addressed_status=_annotator_addressed_status(record.get("annotator_addressed")),
        data_source=data_source,
    )


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
        review_counts = count_completed_iaa_reviews_by_annotation()
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

    user_records = [
        {
            **r,
            "_is_completed": _is_annotation_completed(r),
            "_acceptance_status": _acceptance_status(r.get("isAccept")),
            "_annotator_addressed_status": _annotator_addressed_status(r.get("annotator_addressed")),
        }
        for r in user_records
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

                if (
                    review_counts.get(annotation_id, 0) >= 1
                    and _acceptance_status(record.get("isAccept")) != "needs_restructuring"
                ):
                    return render_template(
                        "load_annotation.html",
                        error="This annotation has already been reviewed and can no longer be edited.",
                        user_records=user_records,
                        review_counts=review_counts
                    )

                # 🔐 Security check — annotators can only load their own
                if (
                    session["user"]["role"] != "admin"
                    and record["annotator_name"] != user
                ):
                    return render_template(
                        "load_annotation.html",
                        error="You can only load your own annotations.",
                        user_records=user_records,
                        review_counts=review_counts
                    )

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
