import os
import json
import datetime
import requests
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

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
            return event['summary']
    return None

def send_pushover(user_key, message):
    requests.post("https://api.pushover.net/1/messages.json", data={
        "token": PUSHOVER_TOKEN,
        "user": user_key,
        "message": message
    })

def send_telegram(user_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": user_id, "text": message})

@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    alert_message = f"[ALERT] {data.get('title', 'No Title')} - {data.get('message', '')}"

    oncall_event = get_current_oncall()
    if not oncall_event:
        return jsonify({"status": "no on-call found"}), 200

    oncall_people = [name.strip() for name in oncall_event.split(", ")]

    final_message = f"On-call: {', '.join(oncall_people)}\n{alert_message}"

    for person in oncall_people:
        if person in CONTACTS:
            send_pushover(CONTACTS[person]["pushover_user_key"], final_message)

    send_telegram(TELEGRAM_GROUP_ID, final_message)

    return jsonify({"status": "sent", "oncall": oncall_people})


