import os
import datetime
import requests
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

# === CONFIG ===
CALENDAR_ID = os.environ.get("CALENDAR_ID")  # Google Calendar ID
GOOGLE_CRED_FILE = os.environ.get("GOOGLE_CRED_FILE")  # path to service account json
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN")
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")  # group chat id

# === GOOGLE CALENDAR SETUP ===
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
creds = service_account.Credentials.from_service_account_file(GOOGLE_CRED_FILE, scopes=SCOPES)
service = build('calendar', 'v3', credentials=creds)

# === FLASK APP ===
app = Flask(__name__)

def get_current_oncall():
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now,
        timeMax=(datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        if start <= datetime.datetime.utcnow().isoformat() <= end:
            return event['summary']  # Person name in event title
    return None

def send_pushover(message):
    requests.post("https://api.pushover.net/1/messages.json", data={
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message
    })

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})

@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    alert_message = f"[ALERT] {data.get('title', 'No Title')} - {data.get('message', '')}"
    
    oncall_person = get_current_oncall()
    if not oncall_person:
        return jsonify({"status": "no on-call found"}), 200

    final_message = f"On-call: {oncall_person}\n{alert_message}"
    
    send_pushover(final_message)
    send_telegram(final_message)
    
    return jsonify({"status": "sent", "oncall": oncall_person})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
