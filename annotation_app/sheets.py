import gspread
from google.oauth2.service_account import Credentials
from config import *
from storage import *

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

#---- for change on pythonanywhere

_client = gspread.authorize(_creds)
_worksheet = _client.open(SHEET_NAME).worksheet(MAIN_SHEET)


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
