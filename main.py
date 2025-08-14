import os
import json
import datetime
import requests
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from dateutil import parser
import logging


load_dotenv()
logging.basicConfig(level=logging.INFO)

required_envs = ["CALENDAR_ID", "GOOGLE_CRED_FILE", "PUSHOVER_TOKEN",
                 "TELEGRAM_BOT_TOKEN", "TELEGRAM_GROUP_ID", "CONTACTS_FILE"]

for var in required_envs:
    if var not in os.environ:
        raise RuntimeError(f"Environment variable {var} is missing")

CALENDAR_ID = os.environ["CALENDAR_ID"]
GOOGLE_CRED_FILE = os.environ["GOOGLE_CRED_FILE"]
PUSHOVER_TOKEN = os.environ["PUSHOVER_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_GROUP_ID = os.environ["TELEGRAM_GROUP_ID"]
CONTACTS_FILE = os.environ["CONTACTS_FILE"]

with open(CONTACTS_FILE, "r") as f:
    CONTACTS = json.load(f)

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
creds = service_account.Credentials.from_service_account_file(GOOGLE_CRED_FILE, scopes=SCOPES)
service = build('calendar', 'v3', credentials=creds)

app = Flask(__name__)

def get_current_oncall():
    # Get calendar timezone
    calendar = service.calendars().get(calendarId=CALENDAR_ID).execute()
    calendar_tz = calendar['timeZone']
    
    now = datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo(calendar_tz))
    time_max = now + datetime.timedelta(days=7)
    
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        if start <= now.isoformat() <= end:
            return event['summary']
    return None

def send_pushover(user_key, message):
    try:
        resp = requests.post("https://api.pushover.net/1/messages.json", data={
            "token": PUSHOVER_TOKEN,
            "user": user_key,
            "message": message,
            "priority": 2,
            "retry": 60,
            "expire": 1800 
        })
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Pushover error for user {user_key}: {e}")
        raise

def send_telegram(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message})
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Telegram error for chat {chat_id}: {e}")
        raise

@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    logging.info(f"Received alert: {data}")
    alert_message = f"[ALERT] {data.get('title', 'No Title')} - {data.get('message', '')}"

    oncall_event = get_current_oncall()
    if not oncall_event:
        return jsonify({"status": "no on-call found"}), 200

    oncall_people = [name.strip() for name in oncall_event.split(", ")]

    final_message = f"On-call: {', '.join(oncall_people)}\n{alert_message}"

    errors = []

    for person in oncall_people:
        if person in CONTACTS:
            try:
                send_pushover(CONTACTS[person]["pushover_user_key"], final_message)
            except Exception:
                errors.append(f"Pushover failed for {person}")
        else:
            logging.warning(f"No Pushover contact found for '{person}'")
            errors.append(f"No contact for {person}")

    try:
        send_telegram(TELEGRAM_GROUP_ID, final_message)
    except Exception:
        errors.append("Telegram failed")

    if errors:
        return jsonify({"status": "partial_failure", "errors": errors, "oncall": oncall_people}), 207
    else:
        return jsonify({"status": "sent", "oncall": oncall_people})

if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "development":
        app.run(host="0.0.0.0", port=5000, debug=True)
