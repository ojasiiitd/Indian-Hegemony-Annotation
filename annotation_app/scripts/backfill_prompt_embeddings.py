#!/usr/bin/env python3
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, APP_DIR)

from sheets import load_records_from_sheet
from prompt_similarity import load_prompt_index, upsert_prompt_embedding_for_record


def main():
    records = load_records_from_sheet()
    index_data = load_prompt_index()
    existing_ids = set(index_data.get("items", {}).keys())

    added = 0
    skipped = 0
    failed = 0

    for record in records:
        annotation_id = record.get("id")
        base_prompt = record.get("prompts", {}).get("base", "")

        if not annotation_id or not str(base_prompt).strip():
            skipped += 1
            continue

        if annotation_id in existing_ids:
            skipped += 1
            continue

        try:
            upsert_prompt_embedding_for_record(record)
            existing_ids.add(annotation_id)
            added += 1
            print(f"Added embedding for: {annotation_id}")
        except Exception as e:
            failed += 1
            print(f"Failed embedding for {annotation_id}: {e}")

    print(f"Backfill complete. Added={added}, Skipped={skipped}, Failed={failed}")


if __name__ == "__main__":
    main()
