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

# 🔑 PUT YOUR OPENROUTER API KEY HERE
API_KEY = os.getenv("API_KEY")


# 🔗 Google Sheets setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")

if not creds_json:
    raise Exception("GOOGLE_CREDENTIALS not set")

creds_dict = json.loads(creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open_by_key("1UN6j6_AhW_XFe--kS7ZJU07XXDQHjwRABF6n1uVpxVQ").sheet1


# ==============================
# 🔍 EXTRACT TEXT (PDF + DOCX)
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

    print("\n=== EXTRACTED TEXT ===")
    print(text[:1000])
    print("=====================\n")

    prompt = f"""
Extract ONLY the following details from this resume:

- Name
- Email
- Phone
- LinkedIn URL (if present, else "")
- Location / Country (if present, else "")
- Highest Education Year (if present, else "")
- Top 5 Skills (short list)
- Total Experience (in years, just number)

Return STRICTLY in this JSON format:

{{
  "name": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "location": "",
  "education_year": "",
  "skills": [],
  "experience": ""
}}

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
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    )

    result = response.json()

    try:
        output = result['choices'][0]['message']['content']
    except:
        output = str(result)

    print("\n=== AI OUTPUT ===")
    print(output)
    print("=================\n")

    # 🔥 Extract clean JSON
    try:
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        clean_json = json_match.group(0)
        data = json.loads(clean_json)
    except Exception as e:
        print("❌ Parsing error:", e)
        print("Raw output:", output)
        return "Error parsing AI response"

    # ==============================
    # 📊 SAVE TO SHEET (FIXED)
    # ==============================
    print("=== BEFORE APPEND ===")
    print(data)

    try:
        row_count = len(sheet.get_all_values()) + 1

        sheet.update(f"A{row_count}:N{row_count}", [[
            data.get("name", ""),
            data.get("email", ""),
            data.get("phone", ""),
            data.get("linkedin", ""),
            data.get("location", ""),
            data.get("education_year", ""),
            ", ".join(data.get("skills", [])),
            data.get("experience", ""),
            "New",
            "",
            datetime.now().strftime("%Y-%m-%d"),
            "",
            "",
            ""
        ]])

        print("✅ ROW ADDED TO SHEET")

    except Exception as e:
        print("❌ ERROR ADDING TO SHEET:", e)
        return "Error saving to Google Sheet"

    return """
    <h2>✅ Resume uploaded successfully!</h2>
    <p>Your profile has been recorded.</p>
    """


# ==============================
# 🚀 TRACK ROUTE
# ==============================
@app.route('/track', methods=['GET'])
def track_application():
    email = request.args.get('email')

    if not email:
        return jsonify({"status": "Enter email"})

    records = sheet.get_all_records()

    for row in records:
        if row.get("Email", "").lower() == email.lower():
            return jsonify({
                "name": row.get("Name", ""),
                "status": row.get("Status", "New"),
                "notes": row.get("Notes", ""),
                "l1_feedback": row.get("L1 Feedback", "")
            })

    return jsonify({"status": "Not Found"})


# ==============================
# 🚀 DASHBOARD APIs
# ==============================
@app.route('/candidates', methods=['GET'])
def get_candidates():
    records = sheet.get_all_records()
    return jsonify(records)


@app.route('/update', methods=['POST'])
def update_candidate():
    data = request.json
    email = data.get("email")

    records = sheet.get_all_records()

    for i, row in enumerate(records):
        if row.get("Email") == email:
            row_number = i + 2

            sheet.update_cell(row_number, 9, data.get("status", ""))
            sheet.update_cell(row_number, 10, data.get("notes", ""))
            sheet.update_cell(row_number, 12, data.get("l1_feedback", ""))

            return jsonify({"message": "Updated successfully"})

    return jsonify({"error": "Candidate not found"}), 404


# ==============================
# 🚀 RUN SERVER
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
