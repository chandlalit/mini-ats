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

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 🔑 API KEY
API_KEY = os.getenv("API_KEY")

# ==============================
# 🔗 GOOGLE SHEETS SETUP (FIXED CLEAN)
# ==============================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")

if not creds_json:
    raise Exception("GOOGLE_CREDENTIALS not set in Render")

# ✅ Parse JSON safely
try:
    creds_dict = json.loads(creds_json)

    if isinstance(creds_dict, str):
        creds_dict = json.loads(creds_dict)

except Exception as e:
    print("❌ JSON ERROR:", e)
    raise

# ✅ Authenticate
try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1UN6j6_AhW_XFe--kS7ZJU07XXDQHjwRABF6n1uVpxVQ").sheet1

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

    else:
        try:
            with open(filepath, 'r', errors='ignore') as f:
                text = f.read()
        except:
            text = ""

    return text


# ==============================
# 🚀 UPLOAD ROUTE
# ==============================
@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['resume']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    text = extract_text(filepath, file.filename)

    prompt = f"""
Extract ONLY the following details from this resume:

- Name
- Email
- Phone
- LinkedIn URL
- Location
- Highest Education Year
- Top 5 Skills
- Total Experience

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

    try:
        output = result['choices'][0]['message']['content']
    except:
        return "Error from AI"

    try:
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        data = json.loads(json_match.group(0))
    except:
        return "Parsing error"

    try:
        row_count = len(sheet.get_all_values()) + 1

        sheet.update(f"A{row_count}:H{row_count}", [[
            data.get("name", ""),
            data.get("email", ""),
            data.get("phone", ""),
            data.get("linkedin", ""),
            data.get("location", ""),
            data.get("education_year", ""),
            ", ".join(data.get("skills", [])),
            data.get("experience", "")
        ]])

    except Exception as e:
        print("Sheet error:", e)
        return "Sheet error"

    return "Uploaded successfully"


# ==============================
# 🚀 TRACK ROUTE
# ==============================
@app.route('/track', methods=['GET'])
def track_application():
    email = request.args.get('email')

    records = sheet.get_all_records()

    for row in records:
        if row.get("Email", "").lower() == email.lower():
            return jsonify(row)

    return jsonify({"status": "Not Found"})


# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
