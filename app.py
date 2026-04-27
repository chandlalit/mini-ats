from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import re
from datetime import datetime
from PyPDF2 import PdfReader
import docx
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
CORS(app)

# ==============================
# 🏠 HOME
# ==============================
@app.route("/")
def home():
    return "Mini ATS is running 🚀"

# ==============================
# 📁 UPLOAD SETUP
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

try:
    creds_dict = json.loads(creds_json)

    # handle double encoded JSON
    if isinstance(creds_dict, str):
        creds_dict = json.loads(creds_dict)

except Exception as e:
    print("❌ JSON ERROR:", e)
    raise

try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1UN6j6_AhW_XFe--kS7ZJU07XXDQHjwRABF6n1uVpxVQ").sheet1
    print("✅ Connected to Google Sheet")

except Exception as e:
    print("❌ GOOGLE AUTH ERROR:", e)
    raise

# ==============================
# 🔍 EXTRACT TEXT
# ==============================
def extract_text(filepath, filename):
    text = ""

    if filename.lower().endswith('.pdf'):
        reader = PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() or ""

    elif filename.lower().endswith('.docx'):
        doc = docx.Document(filepath)
        text = "\n".join([para.text for para in doc.paragraphs])

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

        text = extract_text(filepath, file.filename)
        print("📄 TEXT EXTRACTED")

        prompt = f"""
Extract ONLY the following details:

Name, Email, Phone, LinkedIn, Location, Education Year, Skills, Experience

Return JSON only.

Resume:
{text}
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
        print("🤖 RAW RESPONSE:", result)

        output = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        print("🤖 AI OUTPUT:", output)

        json_match = re.search(r'\{.*\}', output, re.DOTALL)

        if not json_match:
            print("❌ NO JSON FOUND")
            return "AI did not return valid JSON"

        data = json.loads(json_match.group(0))
        print("📊 PARSED DATA:", data)

        # ==============================
        # 📊 WRITE TO GOOGLE SHEET (FINAL FIX)
        # ==============================
        try:
            existing = sheet.get_all_values()
            next_row = len(existing) + 1

            sheet.update(f"A{next_row}:H{next_row}", [[
                data.get("name", ""),
                data.get("email", ""),
                data.get("phone", ""),
                data.get("linkedin", ""),
                data.get("location", ""),
                data.get("education_year", ""),
                ", ".join(data.get("skills", [])),
                data.get("experience", "")
            ]])

            print("✅ DATA WRITTEN TO SHEET AT ROW:", next_row)

        except Exception as e:
            print("❌ SHEET ERROR:", e)
            return f"Sheet error: {str(e)}"

        return "Uploaded successfully"

    except Exception as e:
        print("❌ UPLOAD ERROR:", e)
        return f"Upload error: {str(e)}"

# ==============================
# 🔍 TRACK ROUTE
# ==============================
@app.route('/track', methods=['GET'])
def track_application():
    try:
        email = request.args.get('email')

        records = sheet.get_all_records()

        for row in records:
            if row.get("Email", "").lower() == email.lower():
                return jsonify(row)

        return jsonify({"status": "Not Found"})

    except Exception as e:
        print("❌ TRACK ERROR:", e)
        return f"Track error: {str(e)}"

# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
