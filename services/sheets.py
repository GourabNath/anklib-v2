import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# Define scope
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("anklib_data").sheet1


def save_to_sheets(data: dict):
    """
    Saves user-confirmed book metadata into Google Sheets
    with clean formatting:
    - Sentence case headers
    - Bold header
    - Frozen header row
    - Auto column width
    - Center-aligned numeric columns
    - 🆕 Alternating row colors (zebra striping)
    """

    keys = [
        "timestamp",
        "title",
        "author",
        "publisher",
        "isbn",
        "edition",
        "price",
        "accession_number",
        "number_of_pages"
    ]

    # Format headers → sentence case
    headers = [key.replace("_", " ").capitalize() for key in keys]

    existing_data = sheet.get_all_values()

    if not existing_data:
        sheet.append_row(headers)
    elif existing_data[0] != headers:
        sheet.insert_row(headers, 1)

    # FORMAT HEADER (bold)
    sheet.format("1:1", {
        "textFormat": {"bold": True}
    })

    # FREEZE HEADER ROW
    sheet.freeze(rows=1)

    # Row data
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data.get("title") or "",
        data.get("author") or "",
        data.get("publisher") or "",
        data.get("isbn") or "",
        data.get("edition") or "",
        data.get("price") or "",
        data.get("accession_number") or "",
        data.get("number_of_pages") or ""
    ]

    sheet.append_row(row)

    # AUTO RESIZE COLUMNS
    sheet.columns_auto_resize(0, len(headers))

    # CENTER ALIGN NUMERIC COLUMNS
    sheet.format("G:G", {"horizontalAlignment": "CENTER"})
    sheet.format("I:I", {"horizontalAlignment": "CENTER"})

    # 🆕 =========================
    # 🆕 ZEBRA STRIPING (SAFE)
    # 🆕 =========================

    sheet_id = sheet._properties['sheetId']

    # 🆕 Remove existing banding (prevents stacking issue)
    existing_banding = sheet.spreadsheet.fetch_sheet_metadata()
    requests = []

    for s in existing_banding.get("sheets", []):
        if s["properties"]["sheetId"] == sheet_id:
            banded_ranges = s.get("bandedRanges", [])
            for band in banded_ranges:
                requests.append({
                    "deleteBanding": {
                        "bandedRangeId": band["bandedRangeId"]
                    }
                })

    # 🆕 Add fresh banding
    requests.append({
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,  # Skip header
                    "startColumnIndex": 0,
                    "endColumnIndex": len(headers)
                },
                "rowProperties": {
                    "firstBandColor": {
                        "red": 1,
                        "green": 1,
                        "blue": 1
                    },
                    "secondBandColor": {
                        "red": 0.95,
                        "green": 0.95,
                        "blue": 0.95
                    }
                }
            }
        }
    })

    # 🆕 Apply batch update only if needed
    if requests:
        sheet.spreadsheet.batch_update({"requests": requests})