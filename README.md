# Oncall Notifier

A simple tool to notify team members about on-call schedules.

## Features

- Retrieves schedule from google calendar
- Sends "Emergency Notification" to pushover  (resends every minute for 30 minutes if not aknowledged, this can be configured in the python code)
- Sends notification to telegram group

## Missing Features

- Does not group alerts into incidents which could cause spam (potentially fixable upstream)
- Doesnt escalate an alert to a superviser. At the moment, in order to enable a feature like this, you would need to have 2 way communication on your network to allow people to mark alerts as taken. However, this isnt possible for us at the moment so we are not implementing this.

## How to use google calendar

Its fairly simple, just create an event that lasts the length of a shift, and title it the names of the employs that are on-call during that shift (seperated by a comma and a space). For example, you can title your event: Bob, Alice, George. This will notify all 3 of these people in case of an alert. **But make sure that all these names are in the contact file.**

It is recommended to create a seperate google calendar (settings>Add new calendar>Create new calendar). That way, you can uncheck it so you dont see it when viewing your other calendars on that account.

## Configure webhook in uptime kuma
1. Setup Notification (webook)
2. Set the Post Url to `<domain name>/alert`
3. Set custom body to:
    ```JSON
        { 
            "title": "Uptime Kuma Alert{% if monitorJSON %} - {{ monitorJSON['name'] }}{% endif %}", 
            "message": "{{ msg}}",
            "monitorJSON": {{ monitorJSON | jsonify }}
        }
    ```
    **Note: Templatability is achieved via the Liquid templating language. Please refer to the documentation for usage instructions. These are the available variables: {{msg}}: message of the notification {{heartbeat JSON}}: object describing the heartbeat (only available for UP/DOWN notifications) {{monitorJSON}}: object describing the monitor (only available for UP/DOWN/Certificate expiry notifications)**

4. Set additional headers to:
    ```JSON
        {
            "Content-Type": "application/json"
        }
    ```


## Local development

1. create a .env file with all the required vars.
   - `CALENDAR_ID`
   - `GOOGLE_CRED_FILE`
   - `PUSHOVER_TOKEN`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_GROUP_ID`
   - `CONTACTS_FILE`
   - `FLASK_ENV`
   - `INCIDENTS_FILE`
2. make sure your contacts are formatted as such
    ```json
    {
        "Alice": {
            "pushover_user_key": "PUSHOVER_USER_KEY",
            "telegram_user_id": "TELEGRAM_USER_ID"
        },
        "Bob": {
            "pushover_user_key": "PUSHOVER_USER_KEY",
            "telegram_user_id": "TELEGRAM_USER_ID"
        }
    }
    ```
3. install requirements:
    ```bash
    pip install -r requirements.txt
    ```
4. run the application:
    ```bash
    python main.py
    ```
5. make a test request:
    ```bash
    curl -X POST http://localhost:5000/alert \
        -H "Content-Type: application/json" \
        -d '{
            "title": "Test Alert",
            "message": "This is a test from Uptime Kuma",
            "monitorJSON": {
                "name": "Hello"
            }
        }'
    ```

## Docker local testing
1. build the image for lo
    ```bash
    docker build -t oncall-notifier:local .
    ```

2. run the image to test it locally
   ```bash
    docker run --rm -p 5000:5000 \
        -e CALENDAR_ID="your_calendar_id" \
        -e GOOGLE_CRED_FILE="/config/google-creds.json" \
        -e PUSHOVER_TOKEN="your_pushover_token" \
        -e TELEGRAM_BOT_TOKEN="your_telegram_bot_token" \
        -e TELEGRAM_GROUP_ID="-123456789" \
        -e CONTACTS_FILE="/config/contacts.json" \
        -v <your path to the creds>/config/google-creds.json \
        -v <your path to the contacts>:/config/contacts.json \
        oncall-notifier:local
    ```

## Pushing Docker Image to GitHub Container Registry (GHCR)

1. Authenticate with GHCR
    Use a personal access token (PAT) with write:packages, read:packages, and repo scopes
    ```bash
    echo $GHCR_TOKEN | docker login ghcr.io -u <your_github_username> --password-stdin
    ```

2. Tag your local image
    Replace <repo> with your GitHub repository name
    ```bash
    docker tag oncall-notifier:local ghcr.io/<your_github_username>/<repo>:latest
    ```

3. Push the image
    ```bash
    docker push ghcr.io/<your_github_username>/<repo>:latest
    ```

4. Verify the image
    Visit https://github.com/<your_github_username>?tab=packages to confirm upload


5. Pulling the image (for other users or deployments)
    ```bash
    docker pull ghcr.io/<your_github_username>/<repo>:latest
    ```

