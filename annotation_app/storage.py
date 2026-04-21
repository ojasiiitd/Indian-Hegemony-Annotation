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
    prefix examples:
      - gemini_base
      - gemini_identity
      - gpt_base
      - gpt_identity
      - llama_base
      - llama_identity
      - deepseek_base
      - deepseek_identity
    """

    result = {}

    for axis in HEGEMONY_AXES:
        # NOTE: matches your HTML exactly (axis + "hegemony")
        present = form.get(
            f"{prefix}_{axis}_hegemony",
            "no"
        )

        impact = form.get(
            f"{prefix}_{axis}_impact",
            ""
        ).strip()

        if present == "no" or impact == "" or impact.upper() == "NULL":
            impact = ""

        result[axis] = {
            "present": present,
            "impact": impact
        }

    return result


# =====================================================
# RECORD BUILDER (CANONICAL)
# =====================================================

def build_record(form):
    print("BUILDING 🪭🪭🪭🪭🪭🪭 RECORD")
    return {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),

            "annotator_name": form["annotator_name"],
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
                        "hallucination": "yes" if form.get("gemini_base_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "gemini_base")
                    },
                    "identity": {
                        "text": form.get("gemini_identity_output"),
                        "hallucination": "yes" if form.get("gemini_identity_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "gemini_identity")
                    },
                },

                "gpt": {
                    "base": {
                        "text": form.get("gpt_base_output"),
                        "hallucination": "yes" if form.get("gpt_base_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "gpt_base")
                    },
                    "identity": {
                        "text": form.get("gpt_identity_output"),
                        "hallucination": "yes" if form.get("gpt_identity_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "gpt_identity")
                    },
                },

                "llama": {
                    "base": {
                        "text": form.get("llama_base_output"),
                        "hallucination": "yes" if form.get("llama_base_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "llama_base")
                    },
                    "identity": {
                        "text": form.get("llama_identity_output"),
                        "hallucination": "yes" if form.get("llama_identity_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "llama_identity")
                    },
                },

                "deepseek": {
                    "base": {
                        "text": form.get("deepseek_base_output"),
                        "hallucination": "yes" if form.get("deepseek_base_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "deepseek_base")
                    },
                    "identity": {
                        "text": form.get("deepseek_identity_output"),
                        "hallucination": "yes" if form.get("deepseek_identity_hallucination") == "yes" else "no",
                        "hegemony": extract_hegemony(form, "deepseek_identity")
                    },
                }
            },

            "ground_truth": form.get("ground_truth"),
            "references": form.get("references", ""),
            "expert_reviews": form.get("expert_reviews", ""),
            "isAccept": form.get("isAccept", ""),
            "annotator_addressed": form.get("annotator_addressed", ""),
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
        record["annotator_name"],
        record["region"],
        record["state"],
    ])

    # --- prompts ---
    row.extend([
        record["prompts"]["base"],
        record["prompts"]["identity"],
    ])

    def append_output(block):
        """
        block = {
          "text": "...",
          "hallucination": "...",
          "hegemony": {
              axis: { "present": "yes/no", "impact": str }
          }
        }
        """

        # 1️⃣ text
        row.append(block.get("text", ""))

        # 2️⃣ hallucination
        row.append(block.get("hallucination", ""))

        # 3️⃣ hegemony axes
        for axis in HEGEMONY_AXES:
            axis_data = block["hegemony"].get(axis, {})
            row.append(axis_data.get("present", "no"))
            row.append(axis_data.get("impact", ""))

    # ========= GEMINI =========
    append_output(record["outputs"]["gemini"]["base"])
    append_output(record["outputs"]["gemini"]["identity"])

    # ========= GPT =========
    append_output(record["outputs"]["gpt"]["base"])
    append_output(record["outputs"]["gpt"]["identity"])

    # ========= LLAMA =========
    append_output(record["outputs"]["llama"]["base"])
    append_output(record["outputs"]["llama"]["identity"])

    # ========= DeepSeek =========
    append_output(record["outputs"]["deepseek"]["base"])
    append_output(record["outputs"]["deepseek"]["identity"])

    # --- ground truth ---
    row.append(record.get("ground_truth", ""))

    # --- references ---
    row.append(record.get("references", ""))

    # --- expert review metadata ---
    row.append(record.get("expert_reviews", ""))
    row.append(record.get("isAccept", ""))
    row.append(record.get("annotator_addressed", ""))

    return row
