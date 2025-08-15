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
                 "TELEGRAM_BOT_TOKEN", "TELEGRAM_GROUP_ID", "CONTACTS_FILE", "INCIDENTS_FILE"]

for var in required_envs:
    if var not in os.environ:
        raise RuntimeError(f"Environment variable {var} is missing")

INCIDENTS_FILE = "incidents.json"
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

def load_incidents():
    if not os.path.exists(INCIDENTS_FILE):
        with open(INCIDENTS_FILE, "w") as f:
            json.dump([], f)
    with open(INCIDENTS_FILE, "r") as f:
        return json.load(f)
    return []

def save_incidents(incidents):
    with open(INCIDENTS_FILE, "w") as f:
        json.dump(incidents, f, indent=2)


def get_current_oncall():
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
        logging.info(f"Pushover notification sent for user {user_key}")
    except Exception as e:
        logging.error(f"Pushover error for user {user_key}: {e}")
        raise

def send_telegram(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message})
        resp.raise_for_status()
        logging.info(f"Telegram notification sent to chat {chat_id}")
    except Exception as e:
        logging.error(f"Telegram error for chat {chat_id}: {e}")
        raise


def resolve_incident(existing_incident, incidents, now_ts, data):
    existing_incident["status"] = "resolved"
    existing_incident["resolvedTS"] = now_ts
    existing_incident["alerts"].append({
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data": data
    })
    save_incidents(incidents)
    logging.info(f"Incident resolved: {existing_incident['monitor_name']} at {datetime.datetime.fromtimestamp(now_ts)}")

def find_and_update_existing_incident(incidents, monitor_name, data, now_ts):
    for inc in incidents:
        if (inc["monitor_name"] == monitor_name and
            inc["status"] == "firing"):
            return inc
    return None

@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    logging.info(f"Received alert: {data}")

    monitor_name = None
    if "monitorJSON" in data:
        monitor_name = data["monitorJSON"].get("name")
    if not monitor_name:
        return jsonify({"status": "error", "error": "No monitor name provided"}), 400

    state = "resolved" if "Up]" in data.get("message", "") else "firing"
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()

    incidents = load_incidents()
    existing_incident = find_and_update_existing_incident(incidents, monitor_name, data, now_ts)

    if state == "resolved":
        if existing_incident:
            resolve_incident(existing_incident, incidents, now_ts, data)
            send_telegram(TELEGRAM_GROUP_ID, f"Incident resolved: {monitor_name}")
    else:
        new_incident = None
        if (existing_incident and now_ts - existing_incident["lastNotificationSentTS"] > 86400):
            existing_incident["lastNotificationSentTS"] = now_ts
            new_incident = existing_incident
            logging.info(f"Old Incident updated: {existing_incident['monitor_name']} at {datetime.datetime.fromtimestamp(now_ts)}")
        elif existing_incident:
            existing_incident["alerts"].append({
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data": data
            })
            logging.info(f"Incident updated: {existing_incident['monitor_name']} at {datetime.datetime.fromtimestamp(now_ts)}")
        else:
            new_incident = {
                "id": len(incidents) + 1,
                "monitor_name": monitor_name,
                "status": "firing",
                "firstOccurrenceTS": now_ts,
                "lastNotificationSentTS": now_ts,
                "alerts": [{
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "data": data
                }]
            }
            incidents.append(new_incident)
            logging.info(f"New incident created: {new_incident['monitor_name']} at {datetime.datetime.fromtimestamp(now_ts)}")

        save_incidents(incidents)

        oncall_event = get_current_oncall()

        if not oncall_event:
            return jsonify({"status": "no on-call found"}), 200
        
        if (oncall_event  and new_incident):
            oncall_people = [name.strip() for name in oncall_event.split(", ")]
            final_message = f"On-call: {', '.join(oncall_people)}\n[ALERT] {monitor_name} - {data.get('message', '')}"
            errors = []
            for person in oncall_people:
                if person in CONTACTS:
                    try:
                        send_pushover(CONTACTS[person]["pushover_user_key"], final_message)
                    except Exception:
                        errors.append(f"Pushover failed for {person}")
                else:
                    errors.append(f"No contact for {person}")
            try:
                send_telegram(TELEGRAM_GROUP_ID, final_message)
            except Exception:
                errors.append("Telegram failed")
            return jsonify({"status": "sent", "errors": errors}), 200

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "development":
        app.run(host="0.0.0.0", port=5000, debug=True)