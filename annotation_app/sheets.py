import gspread
from google.oauth2.service_account import Credentials
from config import *
from storage import *
from gspread.exceptions import WorksheetNotFound

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

_creds = Credentials.from_service_account_file(
    GOOGLE_CREDS_PATH,
    scopes=SCOPES
)

MAIN_SHEET = "testing"
BACKUP_SHEET = "testing2"
REVIEW_SHEET = "testreview"

#---- for change on pythonanywhere

REVIEW_HEADERS = [
    "review_id",
    "annotation_id",
    "reviewer_username",
    "region",
    "state",
    "model",
    "prompt_type",
    "Q0_hegemony_present",
    "Q1_axes_correct",
    "Q2_impact_correct",
    "Q3_severity",
    "ground_truth_rating",
    "needs_adjudication",
    "timestamp",
]

_client = gspread.authorize(_creds)
_worksheet = _client.open(SHEET_NAME).worksheet(MAIN_SHEET)


def _ensure_sheet_headers(worksheet, headers):
    existing_headers = worksheet.row_values(1)
    if existing_headers == headers:
        return

    worksheet.resize(cols=max(worksheet.col_count, len(headers)))
    worksheet.update(
        f"A1:{gspread.utils.rowcol_to_a1(1, len(headers))}",
        [headers],
        value_input_option="RAW"
    )


def _normalize_yes_no(value: str) -> str:
    return "yes" if str(value).strip().lower() == "yes" else "no"


def _row_map_to_record(row_map: dict) -> dict:
    record = {
        "id": str(row_map.get("id", "")).strip(),
        "timestamp": row_map.get("timestamp", ""),
        "annotator_name": row_map.get("annotator_name", ""),
        "region": row_map.get("region", ""),
        "state": row_map.get("state", ""),
        "prompts": {
            "base": row_map.get("base_prompt", ""),
            "identity": row_map.get("identity_prompt", ""),
        },
        "outputs": {},
        "ground_truth": row_map.get("ground_truth", ""),
        "references": row_map.get("references", ""),
        "expert_reviews": row_map.get("expert_reviews", ""),
        "isAccept": row_map.get("isAccept", ""),
        "annotator_addressed": row_map.get("annotator_addressed", ""),
    }

    for model in ["gemini", "gpt", "llama", "deepseek"]:
        record["outputs"][model] = {}
        for kind in ["base", "identity"]:
            prefix = f"{model}_{kind}"
            hegemony = {}

            for axis in HEGEMONY_AXES:
                present = _normalize_yes_no(row_map.get(f"{prefix}_{axis}", "no"))
                impact = row_map.get(f"{prefix}_{axis}_impact", "")
                if present == "no":
                    impact = ""
                hegemony[axis] = {
                    "present": present,
                    "impact": impact,
                }

            record["outputs"][model][kind] = {
                "text": row_map.get(f"{prefix}_output", ""),
                "hallucination": _normalize_yes_no(row_map.get(f"{prefix}_hallucination", "no")),
                "hegemony": hegemony,
            }

    return record


def load_records_from_sheet() -> list:
    """
    Read records from the primary worksheet and convert flattened rows
    back into the nested annotation JSON shape used by the app.
    """
    _ensure_sheet_headers(_worksheet, HEADERS)
    values = _worksheet.get_all_values()

    if not values or len(values) < 2:
        return []

    headers = values[0]
    records = []

    for row in values[1:]:
        if not any(str(cell).strip() for cell in row):
            continue

        padded_row = row + [""] * max(0, len(headers) - len(row))
        row_map = {headers[i]: padded_row[i] for i in range(len(headers))}
        record = _row_map_to_record(row_map)

        if record["id"]:
            records.append(record)

    return records


def _get_or_create_review_worksheet():
    spreadsheet = _client.open(SHEET_NAME)

    try:
        worksheet = spreadsheet.worksheet(REVIEW_SHEET)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=REVIEW_SHEET,
            rows=2000,
            cols=max(len(REVIEW_HEADERS), 16)
        )
        worksheet.update("A1", [REVIEW_HEADERS], value_input_option="RAW")
        return worksheet

    header_values = worksheet.row_values(1)
    if not header_values:
        worksheet.update("A1", [REVIEW_HEADERS], value_input_option="RAW")

    return worksheet


def append_review_rows(rows: list):
    if not rows:
        return

    for row in rows:
        if len(row) != len(REVIEW_HEADERS):
            raise ValueError(
                f"Review row length {len(row)} != header length {len(REVIEW_HEADERS)}"
            )

    worksheet = _get_or_create_review_worksheet()
    worksheet.append_rows(rows, value_input_option="RAW")


def _normalize_header_name(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _resolve_review_indices(values: list):
    """
    Resolve annotation/reviewer column indices even if header names vary
    (or if the sheet has no header row).
    Returns: (annotation_idx, reviewer_idx, data_rows)
    """
    if not values:
        return None, None, []

    first_row = values[0]
    normalized_first_row = [_normalize_header_name(v) for v in first_row]

    if "annotation_id" in normalized_first_row:
        annotation_idx = normalized_first_row.index("annotation_id")
        if "reviewer_username" in normalized_first_row:
            reviewer_idx = normalized_first_row.index("reviewer_username")
        else:
            reviewer_idx = REVIEW_HEADERS.index("reviewer_username")
        return annotation_idx, reviewer_idx, values[1:]

    # Fallback: treat entire sheet as data with default column order
    annotation_idx = REVIEW_HEADERS.index("annotation_id")
    reviewer_idx = REVIEW_HEADERS.index("reviewer_username")
    return annotation_idx, reviewer_idx, values


def get_reviewed_annotation_ids_by_user(username: str) -> set:
    worksheet = _get_or_create_review_worksheet()
    values = worksheet.get_all_values()

    if not values:
        return set()

    annotation_idx, reviewer_idx, data_rows = _resolve_review_indices(values)
    if annotation_idx is None or reviewer_idx is None:
        return set()

    reviewed_ids = set()
    for row in data_rows:
        if len(row) <= max(annotation_idx, reviewer_idx):
            continue
        if row[reviewer_idx].strip() == username and row[annotation_idx].strip():
            reviewed_ids.add(row[annotation_idx].strip())

    return reviewed_ids


def get_completed_review_counts_by_annotation(rows_per_reviewer: int = 9) -> dict:
    """
    Return {annotation_id: completed_reviewer_count}.
    A completed review is counted per `rows_per_reviewer` rows.
    """
    worksheet = _get_or_create_review_worksheet()
    values = worksheet.get_all_values()

    if not values:
        return {}

    # Resolve annotation_id column robustly, even if header is missing/altered.
    first_row = values[0]
    normalized_first_row = [_normalize_header_name(v) for v in first_row]

    if "annotation_id" in normalized_first_row:
        annotation_idx = normalized_first_row.index("annotation_id")
        data_rows = values[1:]
    else:
        annotation_idx = REVIEW_HEADERS.index("annotation_id")
        data_rows = values

    raw_counts = {}
    for row in data_rows:
        if len(row) <= annotation_idx:
            continue
        annotation_id = row[annotation_idx].strip()
        if not annotation_id:
            continue
        raw_counts[annotation_id] = raw_counts.get(annotation_id, 0) + 1

    return {
        annotation_id: (row_count // rows_per_reviewer)
        for annotation_id, row_count in raw_counts.items()
    }


def append_row(row: list):
    """
    Append a row to the primary worksheet and a backup sheet (Sheet2).
    Minimal change, defensive, schema-safe.
    """

    print("✖️✖️✖️✖️✖️ APPEND ROW SHEETS CALLED")

    # ---------------------------
    # 1. Schema safety check
    # ---------------------------
    if len(row) != len(HEADERS):
        raise ValueError(
            f"Row length {len(row)} != header length {len(HEADERS)}"
        )

    # ---------------------------
    # 2. Append to primary sheet
    # ---------------------------
    try:
        _ensure_sheet_headers(_worksheet, HEADERS)
        _worksheet.append_row(row, value_input_option="RAW")
        primary_ok = True
    except Exception as e:
        primary_ok = False
        primary_error = e
        print("❌ Failed to append to primary sheet")
        print(e)

    # ---------------------------
    # 3. Append to backup sheet
    # ---------------------------
    try:
        backup_ws = _client.open(SHEET_NAME).worksheet(BACKUP_SHEET)
        _ensure_sheet_headers(backup_ws, HEADERS)
        backup_ws.append_row(row, value_input_option="RAW")
        backup_ok = True
    except Exception as e:
        backup_ok = False
        print("⚠️ Failed to append to backup sheet (Sheet2)")
        print(e)

    # ---------------------------
    # 4. Final decision
    # ---------------------------
    if not primary_ok and not backup_ok:
        raise RuntimeError(
            "Failed to write row to BOTH primary and backup sheets"
        )

    if primary_ok and not backup_ok:
        print("✅ Primary written, ⚠️ backup failed")

    if not primary_ok and backup_ok:
        print("⚠️ Primary failed, ✅ backup written")


def clear_sheet_data():
    _ensure_sheet_headers(_worksheet, HEADERS)
    print("Clearing worksheet:", _worksheet.title)
    rows = _worksheet.row_count
    if rows > 1:
        _worksheet.delete_rows(2, rows)


def rebuild_sheet_from_records(records):
    clear_sheet_data()

    rows = [json_to_row(r) for r in records]

    if not rows:
        return

    # safety check
    for row in rows:
        if len(row) != len(HEADERS):
            raise ValueError(
                f"Row length {len(row)} != header length {len(HEADERS)}"
            )

    _worksheet.append_rows(rows, value_input_option="RAW")

def update_row_by_id(record_id: str, row: list):
    """
    Update a single row in both primary and backup sheets
    based on annotation ID (column 1).
    """

    if len(row) != len(HEADERS):
        raise ValueError(
            f"Row length {len(row)} != header length {len(HEADERS)}"
        )

    # -------- PRIMARY --------
    _ensure_sheet_headers(_worksheet, HEADERS)
    cell = _worksheet.find(record_id)

    if not cell:
        raise ValueError(f"Record ID {record_id} not found in primary sheet")

    row_number = cell.row

    _worksheet.update(
        f"A{row_number}:{gspread.utils.rowcol_to_a1(row_number, len(HEADERS))}",
        [row],
        value_input_option="RAW"
    )

    # -------- BACKUP --------
    try:
        backup_ws = _client.open(SHEET_NAME).worksheet(BACKUP_SHEET)
        _ensure_sheet_headers(backup_ws, HEADERS)
        backup_cell = backup_ws.find(record_id)

        if backup_cell:
            backup_row_number = backup_cell.row
            backup_ws.update(
                f"A{backup_row_number}:{gspread.utils.rowcol_to_a1(backup_row_number, len(HEADERS))}",
                [row],
                value_input_option="RAW"
            )
    except Exception as e:
        print("⚠️ Backup update failed:", e)
 
