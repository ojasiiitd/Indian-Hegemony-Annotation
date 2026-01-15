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
_worksheet = _client.open(SHEET_NAME).sheet1


def append_row(row: list):
    _worksheet.append_row(row, value_input_option="RAW")

def clear_sheet():
    _worksheet.clear()

def rebuild_sheet_from_records(records):
    clear_sheet()

    # Write header row
    _worksheet.append_row(HEADERS)

    for record in records:
        _worksheet.append_row(json_to_row(record))