from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import re
import requests
import gspread
from google.oauth2.service_account import Credentials
from PyPDF2 import PdfReader
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
sheet = client.open_by_key("1UN6j6_AhW_XFe--kS7ZJU07XXDQHjwRABF6n1uVpxVQ").sheet1

print("✅ Connected to Google Sheet")


# ==============================
# 🧹 SAFE STRING HELPER
# ==============================
def safe_str(value):
    """Convert any AI output value safely to a plain string for Google Sheets."""
    if value is None:
        return ""
    if isinstance(value, list):
        # e.g. skills list → "Python, Java, SQL"
        # e.g. experience list of dicts → join as readable text
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
# 🚀 UPLOAD ROUTE
# ==============================
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        print("🚀 UPLOAD HIT")

        file = request.files.get('resume')
        if not file:
            return "No file uploaded"

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        print("📄 FILE SAVED")

        text = extract_text(filepath, file.filename)

        if not text.strip():
            return "Could not read file"

        print("📄 TEXT EXTRACTED")

        # ==============================
        # 🤖 AI CALL
        # ==============================
        prompt = f"""
Extract the following details from the resume.
Return ONLY valid JSON. All values must be plain strings or a flat list of strings for skills.
Do NOT return nested objects or lists of objects.

{{
  "name": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "location": "",
  "education_year": "",
  "skills": ["skill1", "skill2"],
  "experience": "brief summary as plain text"
}}

Resume:
{text[:4000]}
"""

        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [{"role": "user", "content": prompt}]
            }
        )

        result = response.json()
        print("🔍 RAW AI:", result)

        if "choices" not in result:
            return "AI failed"

        output = result['choices'][0]['message']['content']
        print("🧠 AI OUTPUT:", output)

        # ==============================
        # 🧠 PARSE JSON
        # ==============================
        json_match = re.search(r'\{.*\}', output, re.DOTALL)

        if not json_match:
            return "AI parsing failed"

        data = json.loads(json_match.group(0))
        print("✅ PARSED:", data)

        # ==============================
        # ✅ VALIDATION
        # ==============================
        name = data.get("name") or data.get("Name")
        email = data.get("email") or data.get("Email")

        if not name or not email:
            return "Invalid resume data"

        # ==============================
        # 📊 WRITE TO SHEET
        # ==============================
        sheet.append_row([
            safe_str(name),
            safe_str(email),
            safe_str(data.get("phone")),
            safe_str(data.get("linkedin")),
            safe_str(data.get("location")),
            safe_str(data.get("education_year")),
            safe_str(data.get("skills")),
            safe_str(data.get("experience")),
        ])

        print("✅ DATA WRITTEN")

        return "Uploaded successfully"

    except Exception as e:
        print("❌ ERROR:", e)
        return "Internal Server Error"


# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
