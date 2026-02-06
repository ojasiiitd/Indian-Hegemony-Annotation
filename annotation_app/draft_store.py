import json, os, uuid

DRAFT_DIR = "annotation_app/data/drafts"

os.makedirs(DRAFT_DIR, exist_ok=True)

def save_draft(record):
    draft_id = str(uuid.uuid4())
    path = os.path.join(DRAFT_DIR, f"{draft_id}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return draft_id


def load_draft(draft_id):
    path = os.path.join(DRAFT_DIR, f"{draft_id}.json")
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_draft(draft_id):
    path = os.path.join(DRAFT_DIR, f"{draft_id}.json")
    if os.path.exists(path):
        os.remove(path)
