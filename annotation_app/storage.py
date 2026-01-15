import json
import uuid
import os
from datetime import datetime
from config import DATA_FILE, HEGEMONY_AXES


# =====================================================
# JSONL WRITE / REWRITE
# =====================================================

def write_jsonl(record):
    print("🔥 write_jsonl CALLED", record["id"])
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def rewrite_jsonl(records):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


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


# =====================================================
# HEGEMONY EXTRACTION
# =====================================================

def extract_hegemony(form, prefix):
    """
    Extract hegemony axes for a given (model, prompt_type) prefix,
    e.g. prefix = 'gemini_base', 'gpt_identity'
    """
    result = {}

    for axis in HEGEMONY_AXES:
        present = form.get(f"{prefix}_{axis}_hegemony", "no")
        impact = form.get(f"{prefix}_{axis}_impact", "").strip()

        if present == "no" or impact == "" or impact.upper() == "NULL":
            impact = None

        result[axis] = {
            "present": present,
            "impact": impact
        }

    return result


# =====================================================
# RECORD BUILDER (CANONICAL)
# =====================================================

def build_record(form):
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),

        "region": form["region"],
        "state": form["state"],

        "prompts": {
            "base": form.get("base_prompt"),
            "identity": form.get("identity_primed_prompt"),
        },

        "outputs": {
            "gemini": {
                "base": {
                    "text": form.get("gemini_base_output"),
                    "hegemony": extract_hegemony(form, "gemini_base")
                },
                "identity": {
                    "text": form.get("gemini_identity_output"),
                    "hegemony": extract_hegemony(form, "gemini_identity")
                }
            },
            "gpt": {
                "base": {
                    "text": form.get("gpt_base_output"),
                    "hegemony": extract_hegemony(form, "gpt_base")
                },
                "identity": {
                    "text": form.get("gpt_identity_output"),
                    "hegemony": extract_hegemony(form, "gpt_identity")
                }
            },
            "llama": {
                "base": {
                    "text": form.get("llama_base_output"),
                    "hegemony": extract_hegemony(form, "llama_base")
                },
                "identity": {
                    "text": form.get("llama_identity_output"),
                    "hegemony": extract_hegemony(form, "llama_identity")
                }
            }
        },

        "ground_truth": form.get("ground_truth"),
        "references": form.get("references", "")
    }


# =====================================================
# GOOGLE SHEETS FLATTENING
# =====================================================

def json_to_row(record):
    row = []

    # --- metadata ---
    row.extend([
        record["id"],
        record["timestamp"],
        record["region"],
        record["state"],
    ])

    # --- prompts ---
    row.extend([
        record["prompts"]["base"],
        record["prompts"]["identity"],
    ])

    def append_block(block):
        """
        block = {
          "text": "...",
          "hegemony": { axis: {present, impact}, ... }
        }
        """
        row.append(block["text"])
        for axis in HEGEMONY_AXES:
            row.append(block["hegemony"][axis]["present"])
            row.append(block["hegemony"][axis]["impact"])

    # === GEMINI ===
    append_block(record["outputs"]["gemini"]["base"])
    append_block(record["outputs"]["gemini"]["identity"])

    # === GPT ===
    append_block(record["outputs"]["gpt"]["base"])
    append_block(record["outputs"]["gpt"]["identity"])

    # === LLAMA ===
    append_block(record["outputs"]["llama"]["base"])
    append_block(record["outputs"]["llama"]["identity"])

    # --- ground truth ---
    row.extend([
        record["ground_truth"],
        record["references"],
    ])

    return row