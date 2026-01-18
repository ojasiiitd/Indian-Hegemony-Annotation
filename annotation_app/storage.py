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
                    "hegemony": extract_hegemony(form, "gemini_base")
                },
                "identity": {
                    "text": form.get("gemini_identity_output"),
                    "hegemony": extract_hegemony(form, "gemini_identity")
                },
                "ground_truth": form.get("gemini_ground_truth")
            },
            "gpt": {
                "base": {
                    "text": form.get("gpt_base_output"),
                    "hegemony": extract_hegemony(form, "gpt_base")
                },
                "identity": {
                    "text": form.get("gpt_identity_output"),
                    "hegemony": extract_hegemony(form, "gpt_identity")
                },
                "ground_truth": form.get("gpt_ground_truth")
            },
            "llama": {
                "base": {
                    "text": form.get("llama_base_output"),
                    "hegemony": extract_hegemony(form, "llama_base")
                },
                "identity": {
                    "text": form.get("llama_identity_output"),
                    "hegemony": extract_hegemony(form, "llama_identity")
                },
                "ground_truth": form.get("llama_ground_truth")
            },
            "deepseek": {
                "base": {
                    "text": form.get("deepseek_base_output"),
                    "hegemony": extract_hegemony(form, "deepseek_base")
                },
                "identity": {
                    "text": form.get("deepseek_identity_output"),
                    "hegemony": extract_hegemony(form, "deepseek_identity")
                },
                "ground_truth": form.get("deepseek_ground_truth")
            }
        },
        "references": form.get("references", "")
    }

# Sample Record
# {'id': '6be846a7-6b72-4a2e-be59-16697d592778', 'timestamp': '2026-01-16T07:00:07.407092', 'region': 'South', 'state': 'Andhra Pradesh', 
# 'prompts': {'base': 'sdfsgdh', 'identity': 'as a abc, sdfsgdh'}, 
# 'outputs': 
# {'gemini': 
#   {'base': 
#       {'text': '[Model1 output placeholder]\r\n\r\nsdfsgdh\r\n        ', 
#       'hegemony': {'social': {'present': 'yes', 'impact': 's1'}, 'economic': {'present': 'no', 'impact': ''}, 'religious': {'present': 'no', 'impact': ''}, 'gender': {'present': 'no', 'impact': ''}, 'linguistic': {'present': 'no', 'impact': ''}, 'colorism': {'present': 'no', 'impact': ''}}}, 
#   'identity': {'text': '[Model1 output placeholder]\r\n\r\ngtdfds\r\n        ', 'hegemony': {'social': {'present': 'yes', 'impact': 's1'}, 'economic': {'present': 'no', 'impact': ''}, 'religious': {'present': 'no', 'impact': ''}, 'gender': {'present': 'no', 'impact': ''}, 'linguistic': {'present': 'no', 'impact': ''}, 'colorism': {'present': 'no', 'impact': ''}}}, 'ground_truth': '1'}, 'gpt': {'base': {'text': '[Model2 output placeholder]\r\n\r\nsdfsgdh\r\n        ', 'hegemony': {'social': {'present': 'no', 'impact': ''}, 'economic': {'present': 'yes', 'impact': 'e1'}, 'religious': {'present': 'no', 'impact': ''}, 'gender': {'present': 'no', 'impact': ''}, 'linguistic': {'present': 'no', 'impact': ''}, 'colorism': {'present': 'no', 'impact': ''}}}, 'identity': {'text': '[Model2 output placeholder]\r\n\r\ngtdfds\r\n        ', 'hegemony': {'social': {'present': 'no', 'impact': ''}, 'economic': {'present': 'yes', 'impact': 'e1'}, 'religious': {'present': 'no', 'impact': ''}, 'gender': {'present': 'no', 'impact': ''}, 'linguistic': {'present': 'no', 'impact': ''}, 'colorism': {'present': 'no', 'impact': ''}}}, 'ground_truth': None}, 'llama': {'base': {'text': '[Model3 output placeholder]\r\n\r\nsdfsgdh\r\n        ', 'hegemony': {'social': {'present': 'no', 'impact': ''}, 'economic': {'present': 'no', 'impact': ''}, 'religious': {'present': 'yes', 'impact': 'r1'}, 'gender': {'present': 'no', 'impact': ''}, 'linguistic': {'present': 'no', 'impact': ''}, 'colorism': {'present': 'no', 'impact': ''}}}, 'identity': {'text': '[Model3 output placeholder]\r\n\r\ngtdfds\r\n        ', 'hegemony': {'social': {'present': 'no', 'impact': ''}, 'economic': {'present': 'no', 'impact': ''}, 'religious': {'present': 'yes', 'impact': 'r1'}, 'gender': {'present': 'no', 'impact': ''}, 'linguistic': {'present': 'no', 'impact': ''}, 'colorism': {'present': 'no', 'impact': ''}}}, 'ground_truth': '3'}}, 'references': '123'}


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
          "hegemony": {
              axis: { "present": "yes/no", "impact": str|None }
          }
        }
        """
        row.append(block["text"])
        for axis in HEGEMONY_AXES:
            row.append(block["hegemony"][axis]["present"])
            row.append(block["hegemony"][axis]["impact"])

    # ========= GEMINI =========
    append_output(record["outputs"]["gemini"]["base"])
    append_output(record["outputs"]["gemini"]["identity"])
    row.append(record["outputs"]["gemini"]["ground_truth"])

    # ========= GPT =========
    append_output(record["outputs"]["gpt"]["base"])
    append_output(record["outputs"]["gpt"]["identity"])
    row.append(record["outputs"]["gpt"]["ground_truth"])

    # ========= LLAMA =========
    append_output(record["outputs"]["llama"]["base"])
    append_output(record["outputs"]["llama"]["identity"])
    row.append(record["outputs"]["llama"]["ground_truth"])
    
    # ========= DeepSeek =========
    append_output(record["outputs"]["deepseek"]["base"])
    append_output(record["outputs"]["deepseek"]["identity"])
    row.append(record["outputs"]["deepseek"]["ground_truth"])


    # --- references ---
    row.append(record["references"])

    return row