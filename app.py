from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import re
import requests
import gspread
from google.oauth2.service_account import Credentials
from PyPDF2 import PdfReader
from datetime import datetime
import docx

app = Flask(__name__)
CORS(app)

# ==============================
# 🏠 HOME
# ==============================
@app.route("/")
def home():
    return "Mini ATS is running 🚀"

# ==============================
# 📁 UPLOAD FOLDER
# ==============================
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==============================
# 🔑 API KEY
# ==============================
API_KEY = os.getenv("API_KEY")

# ==============================
# 🔗 GOOGLE SHEETS SETUP
# ==============================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")

if not creds_json:
    raise Exception("GOOGLE_CREDENTIALS not set")

creds_dict = json.loads(creds_json)

if isinstance(creds_dict, str):
    creds_dict = json.loads(creds_dict)

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

spreadsheet = client.open_by_key("1UN6j6_AhW_XFe--kS7ZJU07XXDQHjwRABF6n1uVpxVQ")
sheet        = spreadsheet.sheet1

# ==============================
# 📋 ROLES TAB SETUP
# Auto-creates header if Roles tab is empty
# Columns: A=Role Name, B=Req ID, C=Status
# ==============================
try:
    roles_sheet = spreadsheet.worksheet("Roles")
    # If sheet is empty, add header row
    if not roles_sheet.get_all_values():
        roles_sheet.append_row(["Role Name", "Req ID", "Status"])
        print("✅ Roles tab header created")
except gspread.exceptions.WorksheetNotFound:
    roles_sheet = spreadsheet.add_worksheet(title="Roles", rows=200, cols=5)
    roles_sheet.append_row(["Role Name", "Req ID", "Status"])
    print("✅ Roles tab created from scratch")

print("✅ Connected to Google Sheet")


# ==============================
# 🧹 SAFE STRING HELPER
# ==============================
def safe_str(value):
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(", ".join(str(v) for v in item.values() if v))
            else:
                parts.append(str(item))
        return " | ".join(parts)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items() if v)
    return str(value)


# ==============================
# 📧 CLEAN EMAIL HELPER
# ==============================
def clean_email(value):
    text = safe_str(value)
    match = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', text)
    return match.group(0) if match else text


# ==============================
# 📍 FIND NEXT EMPTY ROW
# Only checks column A to ignore dropdown-only rows
# ==============================
def get_next_row():
    col_a = sheet.col_values(1)
    return len(col_a) + 1


# ==============================
# 📄 TEXT EXTRACTION
# ==============================
def extract_text(filepath, filename):
    text = ""
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() or ""
    elif filename.lower().endswith(".docx"):
        doc = docx.Document(filepath)
        text = "\n".join([p.text for p in doc.paragraphs])
    else:
        try:
            with open(filepath, "r", errors="ignore") as f:
                text = f.read()
        except:
            text = ""
    return text


# ==============================
# 📋 GET ROLES
# Returns all Active roles for candidate dropdown
# ==============================
@app.route('/roles', methods=['GET'])
def get_roles():
    try:
        records = roles_sheet.get_all_records()
        roles = []
        for row in records:
            role_name = str(row.get("Role Name", "")).strip()
            req_id    = str(row.get("Req ID", "")).strip()
            status    = str(row.get("Status", "")).strip().lower()
            if role_name and req_id and status == "active":
                roles.append({
                    "label": f"{role_name} - {req_id}",
                    "value": f"{role_name} - {req_id}"
                })
        return jsonify(roles)
    except Exception as e:
        print("❌ Roles fetch error:", e)
        return jsonify([])


# ==============================
# 📋 GET ALL ROLES (for dashboard management)
# Returns all roles regardless of status
# ==============================
@app.route('/all_roles', methods=['GET'])
def get_all_roles():
    try:
        records = roles_sheet.get_all_records()
        return jsonify(records)
    except Exception as e:
        print("❌ All roles fetch error:", e)
        return jsonify([])


# ==============================
# ➕ ADD ROLE (from dashboard)
# ==============================
@app.route('/add_role', methods=['POST'])
def add_role():
    try:
        data      = request.json
        role_name = data.get("role_name", "").strip()
        req_id    = data.get("req_id", "").strip().upper()
        status    = data.get("status", "Active").strip()

        if not role_name or not req_id:
            return jsonify({"error": "Role Name and Req ID are required"}), 400

        # Check for duplicate Req ID
        records = roles_sheet.get_all_records()
        for row in records:
            if str(row.get("Req ID", "")).strip().upper() == req_id:
                return jsonify({"error": f"Req ID '{req_id}' already exists"}), 400

        roles_sheet.append_row([role_name, req_id, status])
        return jsonify({"message": f"✅ '{role_name} - {req_id}' added successfully"})

    except Exception as e:
        print("❌ Add role error:", e)
        return jsonify({"error": "Failed to add role"}), 500


# ==============================
# 🔄 UPDATE ROLE STATUS (from dashboard)
# ==============================
@app.route('/update_role', methods=['POST'])
def update_role():
    try:
        data   = request.json
        req_id = data.get("req_id", "").strip().upper()
        status = data.get("status", "").strip()

        records = roles_sheet.get_all_records()
        for i, row in enumerate(records):
            if str(row.get("Req ID", "")).strip().upper() == req_id:
                row_number = i + 2
                roles_sheet.update_cell(row_number, 3, status)
                return jsonify({"message": "Role status updated"})

        return jsonify({"error": "Role not found"}), 404

    except Exception as e:
        print("❌ Update role error:", e)
        return jsonify({"error": "Failed to update role"}), 500


# ==============================
# 🚀 UPLOAD ROUTE
# ==============================
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        print("🚀 UPLOAD HIT")

        file = request.files.get('resume')
        if not file:
            return "No file uploaded"

        selected_role = request.form.get("role", "")
        print("🎯 Selected Role:", selected_role)

        safe_filename = re.sub(r'[^\w\-.]', '_', file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
        file.save(filepath)
        print("📄 FILE SAVED:", safe_filename)

        text = extract_text(filepath, safe_filename)

        if not text.strip():
            return "Could not read file"

        print("📄 TEXT EXTRACTED, length:", len(text))

        # ==============================
        # 🤖 AI CALL
        # ==============================
        prompt = f"""
Extract the following details from the resume.
Return ONLY a valid JSON object.
All values must be plain strings. Skills must be a flat list of strings.
Do NOT use nested objects or lists of objects for any field.

{{
  "name": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "location": "",
  "education_year": "",
  "skills": ["skill1", "skill2"],
  "experience": "plain text summary of total experience"
}}

Resume:
{text[:4000]}
"""

        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "openai/gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
        except requests.exceptions.Timeout:
            print("❌ AI TIMEOUT")
            return "AI took too long. Please try again."

        result = response.json()
        print("🔍 RAW AI RESPONSE:", result)

        if "choices" not in result:
            print("❌ No choices in AI response")
            return "AI failed"

        output = result['choices'][0]['message']['content']
        print("🧠 AI OUTPUT:", output)

        # ==============================
        # 🧠 PARSE JSON
        # ==============================
        json_match = re.search(r'\{.*\}', output, re.DOTALL)

        if not json_match:
            print("❌ No JSON found in AI output")
            return "AI parsing failed"

        data = json.loads(json_match.group(0))
        print("✅ PARSED DATA:", data)

        # ==============================
        # ✅ VALIDATION
        # ==============================
        name  = safe_str(data.get("name") or data.get("Name"))
        email = clean_email(data.get("email") or data.get("Email"))

        if not name or not email:
            print("❌ Missing name or email")
            return "Invalid resume data"

        # ==============================
        # 📊 WRITE TO SHEET
        # gspread v6: values first, range second
        # ==============================
        next_row = get_next_row()
        print(f"📝 Writing to row {next_row}")

        row_data = [[
            name,
            email,
            safe_str(data.get("phone")),
            safe_str(data.get("linkedin")),
            safe_str(data.get("location")),
            safe_str(data.get("education_year")),
            safe_str(data.get("skills")),
            safe_str(data.get("experience")),
            "New",                                # Col I  - Status
            "",                                   # Col J  - Notes
            datetime.now().strftime("%Y-%m-%d"),  # Col K  - Date Added
            "",                                   # Col L  - L1 Feedback
            selected_role,                        # Col M  - Role
            "",                                   # Col N  - Role Type
        ]]

        sheet.update(row_data, f'A{next_row}:N{next_row}')
        print(f"✅ DATA WRITTEN to row {next_row}, Role: {selected_role}")

        # Clean up temp file
        try:
            os.remove(filepath)
        except:
            pass

        return "Uploaded successfully"

    except Exception as e:
        print("❌ ERROR:", str(e))
        return "Internal Server Error"


# ==============================
# 🔍 TRACK ROUTE
# ==============================
@app.route('/track', methods=['GET'])
def track_application():
    email = request.args.get('email', '').strip().lower()

    if not email:
        return jsonify({"status": "Enter email"})

    records = sheet.get_all_records()

    for row in records:
        row_email = clean_email(row.get("Email", "")).lower()
        if row_email == email:
            return jsonify({
                "name": row.get("Name", ""),
                "status": row.get("Status", "New"),
                "notes": row.get("Notes", ""),
                "l1_feedback": row.get("L1 Feedback", "")
            })

    return jsonify({"status": "Not Found"})


# ==============================
# 📊 DASHBOARD - GET ALL CANDIDATES
# ==============================
@app.route('/candidates', methods=['GET'])
def get_candidates():
    return jsonify(sheet.get_all_records())


# ==============================
# 📊 DASHBOARD - UPDATE CANDIDATE
# ==============================
@app.route('/update', methods=['POST'])
def update_candidate():
    data = request.json
    email = data.get("email", "").strip().lower()

    records = sheet.get_all_records()

    for i, row in enumerate(records):
        row_email = clean_email(row.get("Email", "")).lower()
        if row_email == email:
            row_number = i + 2
            sheet.update_cell(row_number, 9,  data.get("status", ""))
            sheet.update_cell(row_number, 10, data.get("notes", ""))
            sheet.update_cell(row_number, 12, data.get("l1_feedback", ""))
            return jsonify({"message": "Updated"})

    return jsonify({"error": "Not found"}), 404


# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
