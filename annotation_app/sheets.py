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

_client = gspread.authorize(_creds)
_worksheet = _client.open(SHEET_NAME).worksheet("testing")


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
        backup_ws = _client.open(SHEET_NAME).worksheet("testing2")
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