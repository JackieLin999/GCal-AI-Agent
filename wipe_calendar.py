import pickle
from googleapiclient.discovery import build
from datetime import datetime, timezone, timedelta

def get_calendar_service():
    with open('token.pickle', 'rb') as f:
        creds = pickle.load(f)
    return build('calendar', 'v3', credentials=creds)

def wipe_calendar(days_back=35):
    service = get_calendar_service()
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=days_back)).isoformat()

    print(f"🗑️ Fetching events from the past {days_back} days...")
    events_result = service.events().list(
        calendarId='primary',
        timeMin=past,
        timeMax=now.isoformat(),
        maxResults=500,
        singleEvents=True,
    ).execute()

    events = events_result.get('items', [])
    print(f"Found {len(events)} events. Deleting...")

    for event in events:
        service.events().delete(
            calendarId='primary',
            eventId=event['id']
        ).execute()
        print(f"  ❌ Deleted: {event.get('summary', 'Untitled')}")

    print(f"\n✅ Done! Deleted {len(events)} events.")

if __name__ == "__main__":
    confirm = input("⚠️  This will delete ALL events from the past 30 days. Type 'yes' to confirm: ")
    if confirm.lower() == 'yes':
        wipe_calendar()
    else:
        print("Cancelled.")