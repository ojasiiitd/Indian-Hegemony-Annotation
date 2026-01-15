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
API_KEYS_PATH = "annotation_app/apikeys.json"

HEADERS = [
    "id",
    "timestamp",
    "region",
    "state",
    "model",
    "base_prompt",
    "gemini_base_llm_output",
    "base_social",
    "base_social_impact",
    "base_economic",
    "base_economic_impact",
    "base_religious",
    "base_religious_impact",
    "base_gender",
    "base_gender_impact",
    "base_linguistic",
    "base_linguistic_impact",
    "base_colorism",
    "base_colorism_impact",
    "identity_prompt",
    "gemini_identity_llm_output",
    "identity_social",
    "identity_social_impact",
    "identity_economic",
    "identity_economic_impact",
    "identity_religious",
    "identity_religious_impact",
    "identity_gender",
    "identity_gender_impact",
    "identity_linguistic",
    "identity_linguistic_impact",
    "identity_colorism",
    "identity_colorism_impact",
    "ground_truth",
    "references",
]