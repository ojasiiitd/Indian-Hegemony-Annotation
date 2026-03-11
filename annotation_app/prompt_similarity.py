import json
import math
import os
from datetime import datetime
from json import JSONDecodeError

import requests

from config import KEYS

OPENROUTER_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_EMBEDDING_MODEL = "sentence-transformers/all-minilm-l6-v2"

PROMPT_SIM_THRESHOLD = 0.65
PROMPT_SIM_NEAR_DUP_THRESHOLD = 0.9
PROMPT_SIM_MIN_CHARS = 40
PROMPT_SIM_TOP_K = 5
PROMPT_EMBEDDING_INDEX_PATH = "annotation_app/data/prompt_embeddings.json"


def _ensure_index_dir():
    os.makedirs(os.path.dirname(PROMPT_EMBEDDING_INDEX_PATH), exist_ok=True)


def _normalize_header(value):
    return str(value).strip().lower()


def _normalize_vector(vector):
    norm = math.sqrt(sum((x * x) for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def cosine_similarity(vec_a, vec_b):
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    return float(sum((a * b) for a, b in zip(vec_a, vec_b)))


def embed_prompt_openrouter(prompt):
    response = requests.post(
        OPENROUTER_EMBEDDING_URL,
        headers={
            "Authorization": f"Bearer {KEYS['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        data=json.dumps({
            "model": OPENROUTER_EMBEDDING_MODEL,
            "input": prompt,
        }),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    data = payload.get("data", [])
    if not data or "embedding" not in data[0]:
        raise ValueError(f"Unexpected embedding response: {payload}")

    embedding = data[0]["embedding"]
    if not isinstance(embedding, list) or not embedding:
        raise ValueError("OpenRouter returned an empty embedding.")

    return _normalize_vector([float(x) for x in embedding])


def load_prompt_index():
    _ensure_index_dir()
    if not os.path.exists(PROMPT_EMBEDDING_INDEX_PATH):
        return {"version": 1, "items": {}}

    try:
        with open(PROMPT_EMBEDDING_INDEX_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if not raw:
                return {"version": 1, "items": {}}
            data = json.loads(raw)
    except (OSError, JSONDecodeError):
        # Recover gracefully if file is truncated/empty/invalid.
        return {"version": 1, "items": {}}

    if not isinstance(data, dict):
        return {"version": 1, "items": {}}

    version = data.get("version", 1)
    items = data.get("items", {})
    if not isinstance(items, dict):
        items = {}

    return {"version": version, "items": items}


def save_prompt_index(index_data):
    _ensure_index_dir()
    tmp_path = f"{PROMPT_EMBEDDING_INDEX_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False)
    os.replace(tmp_path, PROMPT_EMBEDDING_INDEX_PATH)


def upsert_prompt_embedding(annotation_id, state, base_prompt, embedding):
    if not annotation_id:
        raise ValueError("annotation_id is required for embedding upsert")

    index_data = load_prompt_index()
    index_data["items"][annotation_id] = {
        "annotation_id": annotation_id,
        "state": state or "",
        "base_prompt": base_prompt or "",
        "embedding": embedding,
        "updated_at": datetime.utcnow().isoformat(),
    }
    save_prompt_index(index_data)


def remove_prompt_embedding(annotation_id):
    if not annotation_id:
        return

    index_data = load_prompt_index()
    if annotation_id in index_data["items"]:
        del index_data["items"][annotation_id]
        save_prompt_index(index_data)


def upsert_prompt_embedding_for_record(record):
    annotation_id = record.get("id")
    state = record.get("state", "")
    base_prompt = record.get("prompts", {}).get("base", "")
    if not base_prompt or _normalize_header(base_prompt) == "":
        return

    embedding = embed_prompt_openrouter(base_prompt)
    upsert_prompt_embedding(annotation_id, state, base_prompt, embedding)


def find_similar_for_state(prompt, state, threshold=PROMPT_SIM_THRESHOLD, top_k=PROMPT_SIM_TOP_K, exclude_annotation_id=None):
    query_embedding = embed_prompt_openrouter(prompt)
    index_data = load_prompt_index()
    items = index_data.get("items", {})
    matches = []

    for annotation_id, item in items.items():
        if exclude_annotation_id and annotation_id == exclude_annotation_id:
            continue

        item_state = item.get("state", "")
        if item_state != state:
            continue

        base_prompt = item.get("base_prompt", "")
        vector = item.get("embedding")
        if not base_prompt or not isinstance(vector, list) or not vector:
            continue

        score = cosine_similarity(query_embedding, vector)
        if score >= threshold:
            matches.append({
                "annotation_id": annotation_id,
                "prompt": base_prompt,
                "similarity": round(float(score), 4),
            })

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:top_k]
