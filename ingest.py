import pickle
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
import chromadb
from chromadb.utils import embedding_functions
from gcal import get_calendar_service

def get_past_events(service, months=3):
    """Fetch event from now to x months ago"""
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=months*30)).isoformat()
    now_str = now.isoformat()

    events_result = service.events().list(
        calendarId='primary',
        timeMin=past,        # start of date range
        timeMax=now_str,     # end of date range (now)
        maxResults=500,      # grab up to 500 events
        singleEvents=True,   # expand recurring events into individual occurrences
        orderBy='startTime'
    ).execute()

    return events_result.get('items', [])

def event_to_text(event):
    """convert a raw event into a readable txt"""
    title = event.get('summary', 'Untitled')
    start = event['start'].get('dateTime', event['start'].get('date', ''))
    try:
        # parse the ISO date string into a datetime object
        dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        day_of_week = dt.strftime('%A')    # e.g. "Monday"
        time_of_day = dt.strftime('%I:%M %p')  # e.g. "09:00 AM"
        date_str = dt.strftime('%Y-%m-%d')     # e.g. "2026-03-11"
    except:
        day_of_week = time_of_day = date_str = ''

    # creating the text
    text = f"{title} on {day_of_week} {date_str} at {time_of_day}"

    # create a description if there's a description
    description = event.get('description', '')
    if description:
        text += f". Notes: {description}"

    return text

def ingest():
    """Pull the calendar, embed all of the events, and store in ChromaDB"""
    service = get_calendar_service()
    events = get_past_events(service, months=3)

    # Set up chroma DB
    client = chromadb.PersistentClient(path="./chroma_db")

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # delete existing collection so re-running gives a clean slate (no duplicates)
    try:
        client.delete_collection("calendar_events")
    except:
        pass  # collection didn't exist yet, that's fine


    collection = client.create_collection(
        name="calendar_events",
        embedding_function=ef
    )

    docs, ids, metadatas = [], [], []
    for i, event in enumerate(events):
        text = event_to_text(event)       # convert event to sentence
        docs.append(text)                 # the text to embed and search
        ids.append(f"event_{i}")          # unique ID for each entry
        metadatas.append({
            "title": event.get('summary', 'Untitled'),
            "start": event['start'].get('dateTime', event['start'].get('date', '')),
        })

    collection.add(documents=docs, ids=ids, metadatas=metadatas)

    print("\n🔍 Test query: 'morning meetings'")
    results = collection.query(query_texts=["morning meetings"], n_results=3)
    for doc in results['documents'][0]:
        print(f"  → {doc}")

    print("\n🔍 Test query: 'evening exercise'")
    results = collection.query(query_texts=["evening exercise"], n_results=3)
    for doc in results['documents'][0]:
        print(f"  → {doc}")

if __name__ == "__main__":
    ingest()