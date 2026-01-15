# app.py
from flask import Flask, render_template, request, redirect, jsonify, url_for
from config import REGION_STATE_MAP, HEGEMONY_AXES
from llm import generate_llm_output
from storage import *
from sheets import *
from flask import session
import json
import os
from config import DATA_FILE

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-later"

def load_records():
    records = []
    if not os.path.exists(DATA_FILE):
        return records

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records

@app.route("/", methods=["GET", "POST"])
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

@app.route("/confirm", methods=["POST"])
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

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    prompt_type = data.get("prompt_type")

    if prompt_type == "base":
        prompt = data.get("base_prompt", "")
    elif prompt_type == "identity":
        prompt = data.get("identity_primed_prompt", "")
    else:
        return jsonify({"error": "Invalid prompt type"}), 400

    if not prompt.strip():
        return jsonify({"error": "Empty prompt"}), 400

    try:
        return jsonify({"text": generate_llm_output(prompt)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/records")
def records():
    records = load_records()
    # show newest first
    records.reverse()
    return render_template("records.html", records=records)

@app.route("/admin")
def admin():
    records = load_records()
    return render_template("admin.html", records=records)


@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    delete_ids = request.form.getlist("delete_ids")

    if not delete_ids:
        return redirect(url_for("admin"))

    records = load_records()

    # Filter out deleted records
    remaining = [r for r in records if r["id"] not in delete_ids]

    # Rewrite JSONL
    rewrite_jsonl(remaining)

    # Rebuild Google Sheet
    try:
        rebuild_sheet_from_records(remaining)
    except Exception as e:
        print("Sheet rebuild failed:", e)

    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)