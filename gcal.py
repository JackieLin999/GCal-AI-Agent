import os
import pickle
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'schedule-agent/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as f:
            pickle.dump(creds, f)

    return build('calendar', 'v3', credentials=creds)


def get_events(service, max_results=50):
    now = datetime.now(timezone.utc).isoformat()
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])


def create_event(service, title, start_time, end_time, description=""):
    event = {
        'summary': title,
        'description': description,
        'start': {'dateTime': start_time, 'timeZone': 'America/Detroit'},
        'end':   {'dateTime': end_time,   'timeZone': 'America/Detroit'},
    }
    return service.events().insert(calendarId='primary', body=event).execute()


# --- Test it ---
if __name__ == "__main__":
    service = get_calendar_service()
    print("✅ Auth successful!")

    # Read upcoming events
    events = get_events(service)
    print(f"\n📅 Your next {len(events)} events:")
    for e in events:
        start = e['start'].get('dateTime', e['start'].get('date'))
        print(f"  {start} — {e.get('summary', 'No title')}")

    # Create a test event
    print("\n✏️ Creating a test event...")
    create_event(
        service,
        title="Test — Schedule Agent",
        start_time="2026-04-28T10:00:00",
        end_time="2026-04-28T11:00:00",
        description="Created by my schedule agent!"
    )
    print("✅ Event created! Check your Google Calendar.")