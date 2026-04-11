import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# -----------------------------
# AUTH
# -----------------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# -----------------------------
# CONFIG
# -----------------------------
FOLDER_ID = os.getenv("GOOGLE_FOLDER_ID")  # 👈 create folder + put ID in env
USER_SHEET_MAP_FILE = "user_sheets.json"


# -----------------------------
# LOAD / SAVE USER MAP
# -----------------------------
def load_user_map():
    if os.path.exists(USER_SHEET_MAP_FILE):
        with open(USER_SHEET_MAP_FILE, "r") as f:
            return json.load(f)
    return {}


def save_user_map(data):
    with open(USER_SHEET_MAP_FILE, "w") as f:
        json.dump(data, f, indent=2)  # ✅ small improvement


# -----------------------------
# 🔍 ADDITION: FIND SHEET BY NAME
# -----------------------------
def find_sheet_by_name(user_email):
    try:
        return client.open(f"Library Metadata - {user_email}").sheet1
    except:
        return None


# -----------------------------
# GET OR CREATE SHEET
# -----------------------------
def get_or_create_sheet(user_email):
    user_map = load_user_map()

    # 🔁 Reuse existing
    if user_email in user_map:
        sheet_id = user_map[user_email]
        try:
            return client.open_by_key(sheet_id).sheet1
        except:
            pass  # ✅ fallback below

    # 🔍 ADDITION: Try recovering existing sheet (Render-safe)
    existing_sheet = find_sheet_by_name(user_email)
    if existing_sheet:
        return existing_sheet

    # 🆕 Create new sheet
    print("Creating sheet for:", user_email)
    spreadsheet = client.create(f"Library Metadata - {user_email}")
    sheet = spreadsheet.sheet1
    print("Sheet created with ID:", spreadsheet.id)
    sheet_id = spreadsheet.id

    # 📁 Move to folder
    if FOLDER_ID:
        drive_service = client.auth.service
        drive_service.files().update(
            fileId=sheet_id,
            addParents=FOLDER_ID,
            removeParents='root',
            fields='id, parents'
        ).execute()

    # 📤 Share with user
    spreadsheet.share(user_email, perm_type='user', role='writer')

    # 💾 Save mapping
    user_map[user_email] = sheet_id
    save_user_map(user_map)

    return sheet


# -----------------------------
# SAVE DATA
# -----------------------------
def save_to_sheets(data: dict, user_email: str):

    sheet = get_or_create_sheet(user_email)

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

    headers = [key.replace("_", " ").capitalize() for key in keys]

    existing_data = sheet.get_all_values()

    if not existing_data:
        sheet.append_row(headers)
    elif existing_data[0] != headers:
        sheet.insert_row(headers, 1)

    # FORMAT HEADER
    sheet.format("1:1", {"textFormat": {"bold": True}})
    sheet.freeze(rows=1)

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

    # AUTO RESIZE
    sheet.columns_auto_resize(0, len(headers))

    # CENTER ALIGN NUMERIC
    sheet.format("G:G", {"horizontalAlignment": "CENTER"})
    sheet.format("I:I", {"horizontalAlignment": "CENTER"})

    # ZEBRA STRIPING
    sheet_id = sheet._properties['sheetId']
    metadata = sheet.spreadsheet.fetch_sheet_metadata()

    requests = []

    for s in metadata.get("sheets", []):
        if s["properties"]["sheetId"] == sheet_id:
            for band in s.get("bandedRanges", []):
                requests.append({
                    "deleteBanding": {
                        "bandedRangeId": band["bandedRangeId"]
                    }
                })

    requests.append({
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(headers)
                },
                "rowProperties": {
                    "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                    "secondBandColor": {"red": 0.85, "green": 0.92, "blue": 1}
                }
            }
        }
    })

    if requests:
        sheet.spreadsheet.batch_update({"requests": requests})