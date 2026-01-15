import json
import uuid
import os
from datetime import datetime
from config import DATA_FILE, HEGEMONY_AXES

def write_jsonl(record):
    print("🔥 write_jsonl CALLED", record["id"])
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def extract_hegemony(form_data, prefix):
    axes = ["social","economic","religious","gender","linguistic","colorism"]

    result = {}
    for axis in axes:
        present = form_data.get(f"{prefix}_{axis}_hegemony", "no")
        impact = form_data.get(f"{prefix}_{axis}_impact", "").strip()

        if present == "no":
            impact = None
        elif impact == "" or impact.upper() == "NULL":
            impact = None

        result[axis] = {
            "present": present,
            "impact": impact
        }
    return result


def build_record(form):
    def extract_hegemony(prefix):
        return {
            axis: {
                "present": form.get(f"{prefix}_{axis}_hegemony", "no"),
                "impact": form.get(f"{prefix}_{axis}_impact", "") or None
            }
            for axis in HEGEMONY_AXES
        }

    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "region": form["region"],
        "state": form["state"],
        "model": None,

        "base": {
            "prompt": form["base_prompt"],
            "llm_output": form["gemini_llm_output_base"],
            "hegemony": extract_hegemony("base")
        },

        "identity_primed": {
            "prompt": form["identity_primed_prompt"],
            "llm_output": form["gemini_llm_output_identity"],
            "hegemony": extract_hegemony("identity")
        },

        "ground_truth": form["ground_truth"],
        "references": form.get("references", "")
    }


def json_to_row(record):
    row = [
        record["id"],
        record["timestamp"],
        record["region"],
        record["state"],
        record.get("model"),
    ]

    # ---- BASE PROMPT ----
    row.append(record["base"]["prompt"])
    row.append(record["base"]["llm_output"])

    for axis in HEGEMONY_AXES:
        row.append(record["base"]["hegemony"][axis]["present"])
        row.append(record["base"]["hegemony"][axis]["impact"])

    # ---- IDENTITY-PRIMED PROMPT ----
    row.append(record["identity_primed"]["prompt"])
    row.append(record["identity_primed"]["llm_output"])

    for axis in HEGEMONY_AXES:
        row.append(record["identity_primed"]["hegemony"][axis]["present"])
        row.append(record["identity_primed"]["hegemony"][axis]["impact"])

    # ---- GROUND TRUTH ----
    row.append(record["ground_truth"])
    row.append(record["references"])

    return row

def load_records():
    records = []
    if not os.path.exists(DATA_FILE):
        return records

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def rewrite_jsonl(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")