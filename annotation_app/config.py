import os

DATA_FILE = "data/annotations.jsonl"

REGION_STATE_MAP = {
    "East": "West Bengal",
    "North": "Bihar",
    "South": "Andhra Pradesh",
    "Central": "Maharashtra",
    "West": "Gujarat"
}

HEGEMONY_AXES = [
    "social",
    "economic",
    "religious",
    "gender",
    "linguistic",
    "colorism"
]

SHEET_NAME = "json-to-sheets-hegemony"

GOOGLE_CREDS_PATH = "annotation_app/accounts/google_creds.json"
API_KEYS_PATH = "annotation_app/accounts/apikeys.json"

HEADERS = [
    # --- metadata ---
    "id",
    "timestamp",
    "region",
    "state",

    # --- prompts ---
    "base_prompt",
    "identity_prompt",

    # === GEMINI BASE ===
    "gemini_base_output",
    "gemini_base_social",
    "gemini_base_social_impact",
    "gemini_base_economic",
    "gemini_base_economic_impact",
    "gemini_base_religious",
    "gemini_base_religious_impact",
    "gemini_base_gender",
    "gemini_base_gender_impact",
    "gemini_base_linguistic",
    "gemini_base_linguistic_impact",
    "gemini_base_colorism",
    "gemini_base_colorism_impact",

    # === GEMINI IDENTITY ===
    "gemini_identity_output",
    "gemini_identity_social",
    "gemini_identity_social_impact",
    "gemini_identity_economic",
    "gemini_identity_economic_impact",
    "gemini_identity_religious",
    "gemini_identity_religious_impact",
    "gemini_identity_gender",
    "gemini_identity_gender_impact",
    "gemini_identity_linguistic",
    "gemini_identity_linguistic_impact",
    "gemini_identity_colorism",
    "gemini_identity_colorism_impact",

    # === GPT BASE ===
    "gpt_base_output",
    "gpt_base_social",
    "gpt_base_social_impact",
    "gpt_base_economic",
    "gpt_base_economic_impact",
    "gpt_base_religious",
    "gpt_base_religious_impact",
    "gpt_base_gender",
    "gpt_base_gender_impact",
    "gpt_base_linguistic",
    "gpt_base_linguistic_impact",
    "gpt_base_colorism",
    "gpt_base_colorism_impact",

    # === GPT IDENTITY ===
    "gpt_identity_output",
    "gpt_identity_social",
    "gpt_identity_social_impact",
    "gpt_identity_economic",
    "gpt_identity_economic_impact",
    "gpt_identity_religious",
    "gpt_identity_religious_impact",
    "gpt_identity_gender",
    "gpt_identity_gender_impact",
    "gpt_identity_linguistic",
    "gpt_identity_linguistic_impact",
    "gpt_identity_colorism",
    "gpt_identity_colorism_impact",

    # === LLAMA BASE ===
    "llama_base_output",
    "llama_base_social",
    "llama_base_social_impact",
    "llama_base_economic",
    "llama_base_economic_impact",
    "llama_base_religious",
    "llama_base_religious_impact",
    "llama_base_gender",
    "llama_base_gender_impact",
    "llama_base_linguistic",
    "llama_base_linguistic_impact",
    "llama_base_colorism",
    "llama_base_colorism_impact",

    # === GPT IDENTITY ===
    "llama_identity_output",
    "llama_identity_social",
    "llama_identity_social_impact",
    "llama_identity_economic",
    "llama_identity_economic_impact",
    "llama_identity_religious",
    "llama_identity_religious_impact",
    "llama_identity_gender",
    "llama_identity_gender_impact",
    "llama_identity_linguistic",
    "llama_identity_linguistic_impact",
    "llama_identity_colorism",
    "llama_identity_colorism_impact",

    # --- ground truth ---
    "ground_truth",
    "references",
]