import csv
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ASSIGNMENTS_PATH = BASE_DIR / "data" / "inter_annotator_review_assignments.json"
ANNOTATIONS_CSV_PATH = BASE_DIR / "data" / "annotations_sheet1.csv"
OUTPUT_PATH = BASE_DIR / "data" / "inter_annotator_review_assignment_visualization.md"


def _title_case_username(username):
    return " ".join(part.capitalize() for part in str(username or "").split())


def _load_assignments():
    with ASSIGNMENTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_annotations():
    rows_by_id = {}
    with ANNOTATIONS_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            annotation_id = str(row.get("id") or "").strip()
            if annotation_id:
                rows_by_id[annotation_id] = row
    return rows_by_id


def _md_escape(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()


def _sorted_annotation_ids(annotation_ids, rows_by_id):
    return sorted(
        annotation_ids,
        key=lambda annotation_id: (
            _md_escape((rows_by_id.get(annotation_id) or {}).get("annotator_name", "")).casefold(),
            _md_escape((rows_by_id.get(annotation_id) or {}).get("base_prompt", "")).casefold(),
            annotation_id,
        ),
    )


def _append_annotation_table(lines, annotation_ids, rows_by_id):
    lines.append("| Sr. No. | ID | Created By | Base Prompt |")
    lines.append("| --- | --- | --- | --- |")
    for index, annotation_id in enumerate(_sorted_annotation_ids(annotation_ids, rows_by_id), start=1):
        row = rows_by_id.get(annotation_id, {})
        lines.append(
            f"| {index} | `{annotation_id}` | {_md_escape(row.get('annotator_name', ''))} | {_md_escape(row.get('base_prompt', ''))} |"
        )


def _build_state_summary_lines(state_name, state_data, rows_by_id):
    selected_ids = state_data.get("selected_annotation_ids", [])
    assignments_by_reviewer = state_data.get("assignments_by_reviewer", {})

    lines = [f"## {state_name.title()}", ""]
    lines.append(f"- Selected review pool: `{len(selected_ids)}` annotations")
    lines.append(f"- Unique selected IDs: `{len(set(selected_ids))}`")
    lines.append("")

    lines.append("### Selected Pool")
    lines.append("")
    _append_annotation_table(lines, selected_ids, rows_by_id)
    lines.append("")

    for reviewer_name, reviewer_ids in assignments_by_reviewer.items():
        lines.append(f"### Reviewer: {_title_case_username(reviewer_name)}")
        lines.append("")
        lines.append(f"- Assigned count: `{len(reviewer_ids)}`")
        lines.append("")
        _append_annotation_table(lines, reviewer_ids, rows_by_id)
        lines.append("")

    return lines


def main():
    assignments = _load_assignments()
    rows_by_id = _load_annotations()

    lines = [
        "# Inter-Annotator Review Assignment Visualization",
        "",
        "Generated directly from `inter_annotator_review_assignments.json` and matched against `annotations_sheet1.csv`.",
        "",
    ]

    for state_name, state_data in assignments.items():
        lines.extend(_build_state_summary_lines(state_name, state_data, rows_by_id))

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
