from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import re
import requests
import gspread
import jwt
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from google.oauth2.service_account import Credentials
from PyPDF2 import PdfReader
from datetime import datetime, timedelta
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
# 🔑 API KEYS & SECRETS
# ==============================
API_KEY      = os.getenv("API_KEY")
JWT_SECRET   = os.getenv("JWT_SECRET", "change-this-secret")
ADMIN_EMAIL  = "chandlalit53@gmail.com"
ADMIN_PASS   = os.getenv("ADMIN_PASSWORD", "Admin@2026")

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
# ==============================
try:
    roles_sheet = spreadsheet.worksheet("Roles")
    if not roles_sheet.get_all_values():
        roles_sheet.append_row(["Role Name", "Req ID", "Status"])
except gspread.exceptions.WorksheetNotFound:
    roles_sheet = spreadsheet.add_worksheet(title="Roles", rows=200, cols=5)
    roles_sheet.append_row(["Role Name", "Req ID", "Status"])

# ==============================
# 👥 USERS TAB SETUP
# Columns: Email | Password Hash | Name | Company | Role | Active | Recruiter ID | Created
# ==============================
try:
    users_sheet = spreadsheet.worksheet("Users")
    if not users_sheet.get_all_values():
        users_sheet.append_row(["Email", "Password Hash", "Name", "Company", "Role", "Active", "Recruiter ID", "Created"])
        # Seed admin account
        users_sheet.append_row([
            ADMIN_EMAIL,
            generate_password_hash(ADMIN_PASS),
            "Admin",
            "Internal",
            "admin",
            "Yes",
            "ADMIN",
            datetime.now().strftime("%Y-%m-%d")
        ])
        print("✅ Users tab created, admin account seeded")
    else:
        # Check if admin exists, create if not
        records = users_sheet.get_all_records()
        admin_exists = any(r.get("Email") == ADMIN_EMAIL for r in records)
        if not admin_exists:
            users_sheet.append_row([
                ADMIN_EMAIL,
                generate_password_hash(ADMIN_PASS),
                "Admin",
                "Internal",
                "admin",
                "Yes",
                "ADMIN",
                datetime.now().strftime("%Y-%m-%d")
            ])
            print("✅ Admin account created")
except gspread.exceptions.WorksheetNotFound:
    users_sheet = spreadsheet.add_worksheet(title="Users", rows=200, cols=10)
    users_sheet.append_row(["Email", "Password Hash", "Name", "Company", "Role", "Active", "Recruiter ID", "Created"])
    users_sheet.append_row([
        ADMIN_EMAIL,
        generate_password_hash(ADMIN_PASS),
        "Admin",
        "Internal",
        "admin",
        "Yes",
        "ADMIN",
        datetime.now().strftime("%Y-%m-%d")
    ])
    print("✅ Users tab + admin created from scratch")

print("✅ Connected to Google Sheet")

# ==============================
# 📊 COLUMN MAP
# ==============================
# A=1  Name          B=2  Email        C=3  Phone
# D=4  LinkedIn      E=5  Location     F=6  Education Year
# G=7  Skills        H=8  Yrs of Exp   I=9  Summary
# J=10 Domain        K=11 Status       L=12 Notes
# M=13 Date Added    N=14 L1 Feedback  O=15 Role
# P=16 Role Type     Q=17 Recruiter ID

COL_STATUS       = 11
COL_NOTES        = 12
COL_L1_FEEDBACK  = 14
COL_RECRUITER_ID = 17


# ==============================
# 🧹 HELPERS
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

def clean_email(value):
    text = safe_str(value)
    match = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', text)
    return match.group(0) if match else text

def get_next_row():
    col_a = sheet.col_values(1)
    return len(col_a) + 1

def generate_recruiter_id():
    return secrets.token_hex(4).upper()  # e.g. "A3F2B1C9"

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
# 🔐 AUTH DECORATORS
# ==============================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Login required"}), 401
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired, please login again"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Login required"}), 401
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            if payload.get("role") != "admin":
                return jsonify({"error": "Admin access only"}), 403
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired, please login again"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# ==============================
# 🔐 LOGIN
# ==============================
@app.route('/login', methods=['POST'])
def login():
    try:
        data     = request.json
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")

        records = users_sheet.get_all_records()

        for user in records:
            if user.get("Email", "").lower() == email:
                if user.get("Active", "").lower() != "yes":
                    return jsonify({"error": "Account is deactivated"}), 403

                if check_password_hash(user.get("Password Hash", ""), password):
                    token = jwt.encode({
                        "email":        email,
                        "name":         user.get("Name", ""),
                        "role":         user.get("Role", "recruiter"),
                        "recruiter_id": user.get("Recruiter ID", ""),
                        "company":      user.get("Company", ""),
                        "exp":          datetime.utcnow() + timedelta(hours=12)
                    }, JWT_SECRET, algorithm="HS256")

                    return jsonify({
                        "token":        token,
                        "role":         user.get("Role", "recruiter"),
                        "name":         user.get("Name", ""),
                        "recruiter_id": user.get("Recruiter ID", "")
                    })

                return jsonify({"error": "Incorrect password"}), 401

        return jsonify({"error": "Email not found"}), 404

    except Exception as e:
        print("❌ Login error:", e)
        return jsonify({"error": "Login failed"}), 500


# ==============================
# 👤 GET CURRENT USER INFO
# ==============================
@app.route('/me', methods=['GET'])
@token_required
def get_me():
    return jsonify(request.user)


# ==============================
# 👥 ADMIN — GET ALL RECRUITERS
# ==============================
@app.route('/recruiters', methods=['GET'])
@admin_required
def get_recruiters():
    try:
        records = users_sheet.get_all_records()
        recruiters = []
        for r in records:
            if r.get("Role") == "recruiter":
                recruiters.append({
                    "email":        r.get("Email"),
                    "name":         r.get("Name"),
                    "company":      r.get("Company"),
                    "active":       r.get("Active"),
                    "recruiter_id": r.get("Recruiter ID"),
                    "created":      r.get("Created")
                })
        return jsonify(recruiters)
    except Exception as e:
        print("❌ Get recruiters error:", e)
        return jsonify([])


# ==============================
# ➕ ADMIN — ADD RECRUITER
# ==============================
@app.route('/add_recruiter', methods=['POST'])
@admin_required
def add_recruiter():
    try:
        data     = request.json
        email    = data.get("email", "").strip().lower()
        name     = data.get("name", "").strip()
        company  = data.get("company", "").strip()
        password = data.get("password", "").strip()

        if not email or not name or not password:
            return jsonify({"error": "Email, name and password are required"}), 400

        # Check duplicate
        records = users_sheet.get_all_records()
        for r in records:
            if r.get("Email", "").lower() == email:
                return jsonify({"error": "Email already exists"}), 400

        rid = generate_recruiter_id()

        users_sheet.append_row([
            email,
            generate_password_hash(password),
            name,
            company,
            "recruiter",
            "Yes",
            rid,
            datetime.now().strftime("%Y-%m-%d")
        ])

        return jsonify({
            "message":      f"✅ Recruiter '{name}' created successfully",
            "recruiter_id": rid
        })

    except Exception as e:
        print("❌ Add recruiter error:", e)
        return jsonify({"error": "Failed to add recruiter"}), 500


# ==============================
# 🔄 ADMIN — TOGGLE RECRUITER
# ==============================
@app.route('/toggle_recruiter', methods=['POST'])
@admin_required
def toggle_recruiter():
    try:
        email  = request.json.get("email", "").strip().lower()
        records = users_sheet.get_all_records()

        for i, r in enumerate(records):
            if r.get("Email", "").lower() == email:
                row_num    = i + 2
                current    = r.get("Active", "Yes")
                new_status = "No" if current == "Yes" else "Yes"
                users_sheet.update_cell(row_num, 6, new_status)
                return jsonify({"message": f"Recruiter {'activated' if new_status == 'Yes' else 'deactivated'}"})

        return jsonify({"error": "Recruiter not found"}), 404

    except Exception as e:
        print("❌ Toggle recruiter error:", e)
        return jsonify({"error": "Failed to update"}), 500


# ==============================
# 📋 GET ACTIVE ROLES (public — for candidate form)
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
                roles.append({"label": f"{role_name} - {req_id}", "value": f"{role_name} - {req_id}"})
        return jsonify(roles)
    except Exception as e:
        print("❌ Roles fetch error:", e)
        return jsonify([])


# ==============================
# 📋 GET ALL ROLES (protected — for dashboard)
# ==============================
@app.route('/all_roles', methods=['GET'])
@token_required
def get_all_roles():
    try:
        return jsonify(roles_sheet.get_all_records())
    except Exception as e:
        print("❌ All roles error:", e)
        return jsonify([])


# ==============================
# ➕ ADD ROLE (protected)
# ==============================
@app.route('/add_role', methods=['POST'])
@token_required
def add_role():
    try:
        data      = request.json
        role_name = data.get("role_name", "").strip()
        req_id    = data.get("req_id", "").strip().upper()
        status    = data.get("status", "Active").strip()

        if not role_name or not req_id:
            return jsonify({"error": "Role Name and Req ID are required"}), 400

        records = roles_sheet.get_all_records()
        for row in records:
            if str(row.get("Req ID", "")).strip().upper() == req_id:
                return jsonify({"error": f"Req ID '{req_id}' already exists"}), 400

        roles_sheet.append_row([role_name, req_id, status])
        return jsonify({"message": f"✅ '{role_name} - {req_id}' added"})

    except Exception as e:
        print("❌ Add role error:", e)
        return jsonify({"error": "Failed to add role"}), 500


# ==============================
# 🔄 UPDATE ROLE STATUS (protected)
# ==============================
@app.route('/update_role', methods=['POST'])
@token_required
def update_role():
    try:
        data   = request.json
        req_id = data.get("req_id", "").strip().upper()
        status = data.get("status", "").strip()

        records = roles_sheet.get_all_records()
        for i, row in enumerate(records):
            if str(row.get("Req ID", "")).strip().upper() == req_id:
                roles_sheet.update_cell(i + 2, 3, status)
                return jsonify({"message": "Role updated"})

        return jsonify({"error": "Role not found"}), 404

    except Exception as e:
        print("❌ Update role error:", e)
        return jsonify({"error": "Failed to update"}), 500


# ==============================
# 🚀 UPLOAD ROUTE (public — candidates use this)
# Recruiter ID passed as query param ?rid=XXXX
# ==============================
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        print("🚀 UPLOAD HIT")

        file = request.files.get('resume')
        if not file:
            return "No file uploaded"

        selected_role = request.form.get("role", "")
        recruiter_id  = request.args.get("rid", "")   # from URL ?rid=XXXX
        print(f"🎯 Role: {selected_role} | Recruiter: {recruiter_id}")

        safe_filename = re.sub(r'[^\w\-.]', '_', file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
        file.save(filepath)
        print("📄 FILE SAVED:", safe_filename)

        text = extract_text(filepath, safe_filename)
        if not text.strip():
            return "Could not read file"

        print("📄 TEXT EXTRACTED, length:", len(text))

        prompt = f"""
You are a resume parser. Extract the following fields from the resume below.
Return ONLY a valid JSON object — no extra text, no markdown, no explanation.

Rules:
- "education_year": Extract the most recent graduation year as a 4-digit year string (e.g. "2019"). Look for degree completion dates, graduation years, or batch years. If multiple degrees, return the most recent year.
- "yrs_of_exp": Calculate total professional work experience as a short string like "6 years" or "8.5 years". Add up all job durations.
- "summary": Write 2 sentences max describing their seniority level, main tech stack, and strongest skills.
- "domain": List industries they have worked in (e.g. "Finance, Healthcare, Retail"). If not clear, write "Not specified".
- "skills": Flat list of technical skills only. No soft skills.

{{
  "name": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "location": "",
  "education_year": "",
  "skills": ["skill1", "skill2"],
  "yrs_of_exp": "",
  "summary": "",
  "domain": ""
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
        if "choices" not in result:
            return "AI failed"

        output = result['choices'][0]['message']['content']
        print("🧠 AI OUTPUT:", output)

        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if not json_match:
            return "AI parsing failed"

        data = json.loads(json_match.group(0))
        print("✅ PARSED DATA:", data)

        name  = safe_str(data.get("name") or data.get("Name"))
        email = clean_email(data.get("email") or data.get("Email"))

        if not name or not email:
            return "Invalid resume data"

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
            safe_str(data.get("yrs_of_exp")),
            safe_str(data.get("summary")),
            safe_str(data.get("domain")),
            "New",
            "",
            datetime.now().strftime("%Y-%m-%d"),
            "",
            selected_role,
            "",
            recruiter_id,       # Q - Recruiter ID
        ]]

        sheet.update(row_data, f'A{next_row}:Q{next_row}')
        print(f"✅ DATA WRITTEN to row {next_row}")

        try:
            os.remove(filepath)
        except:
            pass

        return "Uploaded successfully"

    except Exception as e:
        print("❌ ERROR:", str(e))
        return "Internal Server Error"


# ==============================
# 🔍 TRACK ROUTE (public)
# ==============================
@app.route('/track', methods=['GET'])
def track_application():
    email = request.args.get('email', '').strip().lower()
    if not email:
        return jsonify({"status": "Enter email"})

    records = sheet.get_all_records()
    for row in records:
        if clean_email(row.get("Email", "")).lower() == email:
            return jsonify({
                "name":        row.get("Name", ""),
                "status":      row.get("Status", "New"),
                "notes":       row.get("Notes", ""),
                "l1_feedback": row.get("L1 Feedback", "")
            })

    return jsonify({"status": "Not Found"})


# ==============================
# 📊 GET CANDIDATES (protected)
# Recruiter → only their own
# Admin     → all
# ==============================
@app.route('/candidates', methods=['GET'])
@token_required
def get_candidates():
    try:
        records = sheet.get_all_records()
        role    = request.user.get("role")
        rid     = request.user.get("recruiter_id", "")

        if role == "admin":
            return jsonify(records)

        # Recruiter: filter by their recruiter_id
        filtered = [r for r in records if str(r.get("Recruiter ID", "")).strip() == rid]
        return jsonify(filtered)

    except Exception as e:
        print("❌ Get candidates error:", e)
        return jsonify([])


# ==============================
# 📊 UPDATE CANDIDATE (protected)
# ==============================
@app.route('/update', methods=['POST'])
@token_required
def update_candidate():
    data  = request.json
    email = data.get("email", "").strip().lower()
    role  = request.user.get("role")
    rid   = request.user.get("recruiter_id", "")

    records = sheet.get_all_records()

    for i, row in enumerate(records):
        if clean_email(row.get("Email", "")).lower() == email:
            # Recruiters can only update their own candidates
            if role != "admin" and str(row.get("Recruiter ID", "")).strip() != rid:
                return jsonify({"error": "Not authorized"}), 403

            row_number = i + 2
            sheet.update_cell(row_number, COL_STATUS,       data.get("status", ""))
            sheet.update_cell(row_number, COL_NOTES,        data.get("notes", ""))
            sheet.update_cell(row_number, COL_L1_FEEDBACK,  data.get("l1_feedback", ""))
            return jsonify({"message": "Updated"})

    return jsonify({"error": "Not found"}), 404


# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
