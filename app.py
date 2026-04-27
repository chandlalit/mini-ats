from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
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
# 📁 UPLOAD FOLDER
# ==============================
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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

# Fix double encoding (important)
if isinstance(creds_dict, str):
    creds_dict = json.loads(creds_dict)

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open_by_key("1UN6j6_AhW_XFe--kS7ZJU07XXDQHjwRABF6n1uVpxVQ").sheet1

print("✅ Connected to Google Sheet")

# ==============================
# 🚀 UPLOAD ROUTE (LIGHT VERSION)
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

        # 🔥 NO AI — dummy data (to avoid crash)
        data = {
            "name": "Test User",
            "email": "test@example.com",
            "phone": "1234567890",
            "linkedin": "linkedin.com/test",
            "location": "India",
            "education_year": "2024",
            "skills": ["Python", "AI"],
            "experience": "1 year"
        }

        existing = sheet.get_all_values()
        next_row = len(existing) + 1

        sheet.update(f"A{next_row}:H{next_row}", [[
            data["name"],
            data["email"],
            data["phone"],
            data["linkedin"],
            data["location"],
            data["education_year"],
            ", ".join(data["skills"]),
            data["experience"]
        ]])

        print("✅ DATA WRITTEN TO SHEET")

        return "Uploaded successfully"

    except Exception as e:
        print("❌ ERROR:", e)
        return f"Error: {str(e)}"

# ==============================
# 🚀 RUN
# ==============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
