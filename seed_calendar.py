import pickle
from datetime import datetime, timezone, timedelta
import random
from googleapiclient.discovery import build

def get_calendar_service():
    with open('token.pickle', 'rb') as f:
        creds = pickle.load(f)
    return build('calendar', 'v3', credentials=creds)

def create_event(service, title, start_dt, end_dt, description=""):
    event = {
        'summary': title,
        'description': description,
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/Detroit'},
        'end':   {'dateTime': end_dt.isoformat(),   'timeZone': 'America/Detroit'},
    }
    return service.events().insert(calendarId='primary', body=event).execute()

# --- Define recurring patterns (like a real student's life) ---
weekly_events = [
    # (day_of_week, hour, minute, duration_hours, title)
    # 0=Monday, 1=Tuesday, ...
    (0, 9,  0, 1.5, "Algorithms Lecture"),
    (0, 14, 0, 1.0, "Study Group — Algorithms"),
    (1, 10, 0, 1.5, "Machine Learning Lecture"),
    (1, 18, 0, 1.0, "Gym"),
    (2, 9,  0, 1.5, "Algorithms Lecture"),
    (2, 13, 0, 2.0, "Deep Work — Coding"),
    (3, 10, 0, 1.5, "Machine Learning Lecture"),
    (3, 18, 0, 1.0, "Gym"),
    (4, 11, 0, 1.0, "Office Hours"),
    (4, 15, 0, 2.0, "Project Work"),
    (5, 10, 0, 1.5, "Deep Work — Side Project"),
    (5, 14, 0, 1.0, "Grocery Run"),
    (6, 11, 0, 1.0, "Brunch"),
    (6, 15, 0, 2.0, "Chill / Gaming"),
]

# One-off events sprinkled in
one_off_events = [
    (27, 14, 0, 1.0, "Resume Review with Career Center"),
    (25, 10, 0, 0.5, "Dentist Appointment"),
    (22, 15, 0, 2.0, "Hackathon Kickoff"),
    (21, 9,  0, 3.0, "Hackathon — final push"),
    (18, 13, 0, 1.0, "Lunch with Prof. Smith"),
    (15, 16, 0, 1.5, "ML Assignment due — last push"),
    (12, 18, 0, 2.0, "Movie Night with Friends"),
    (10, 9,  0, 2.0, "Midterm — Algorithms"),
    (7,  14, 0, 1.0, "1:1 with Research Advisor"),
    (5,  10, 0, 1.0, "Career Fair Prep"),
    (3,  17, 0, 1.5, "Team Dinner"),
    (1,  9,  0, 2.0, "Final Project Planning"),
]

def seed_calendar():
    service = get_calendar_service()

    import zoneinfo
    TZ = zoneinfo.ZoneInfo("America/Detroit")
    now = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)


    created = 0

    print("Creating weekly recurring events for past 30 days...")
    for days_ago in range(30, 0, -1):
        day = now - timedelta(days=days_ago)
        day_of_week = day.weekday()

        for (dow, hour, minute, duration, title) in weekly_events:
            if dow == day_of_week:
                # Add some randomness so it feels real
                offset = random.randint(-10, 10)
                start = day.replace(hour=hour, minute=minute) + timedelta(minutes=offset)
                end = start + timedelta(hours=duration)
                create_event(service, title, start, end)
                created += 1

    print("Creating one-off events...")
    for (days_ago, hour, minute, duration, title) in one_off_events:
        day = now - timedelta(days=days_ago)
        start = day.replace(hour=hour, minute=minute)
        end = start + timedelta(hours=duration)
        create_event(service, title, start, end)
        created += 1

    print(f"✅ Done! Created {created} events. Check your Google Calendar.")

if __name__ == "__main__":
    seed_calendar()