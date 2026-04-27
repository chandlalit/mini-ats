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
        file = request.files['resume']
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        text = extract_text(filepath, file.filename)

        print("📄 EXTRACTED TEXT (first 300 chars):")
        print(text[:300])

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
        print("🤖 RAW AI RESPONSE:", result)

        output = result.get('choices', [{}])[0].get('message', {}).get('content', '')

        print("🤖 AI OUTPUT:", output)

        # Extract JSON safely
        try:
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if not json_match:
                raise Exception("No JSON found in AI response")

            data = json.loads(json_match.group(0))

        except Exception as e:
            print("❌ PARSE ERROR:", e)
            return f"Parse error: {str(e)}"

        print("📊 FINAL DATA:", data)

        # ==============================
        # 📊 WRITE TO GOOGLE SHEET
        # ==============================
        try:
            sheet.append_row([
                data.get("name", ""),
                data.get("email", ""),
                data.get("phone", ""),
                data.get("linkedin", ""),
                data.get("location", ""),
                data.get("education_year", ""),
                ", ".join(data.get("skills", [])),
                data.get("experience", "")
            ])

            print("✅ SUCCESS: DATA WRITTEN TO SHEET")

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
        return f"Track error: {str(e)}"


# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
