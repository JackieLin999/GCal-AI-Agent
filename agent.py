import json
import re
import zoneinfo
from datetime import datetime, timezone, timedelta
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch
import chromadb
from chromadb.utils import embedding_functions
from gcal import get_calendar_service, create_event

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
TZ = zoneinfo.ZoneInfo("America/Detroit")

# ── 1. Load LLM ──────────────────────────────────────────────────────────────

def load_model():
    print("📥 Loading model...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    print("Model loaded!")
    return model, tokenizer


def ask(model, tokenizer, prompt, system):
    """Send a prompt to the model and return the response"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
    generated = outputs[0][inputs.input_ids.shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True)


# ── 2. Load ChromaDB ──────────────────────────────────────────────────────────

def load_rag():
    """Connect to the ChromaDB collection we built in ingest.py"""
    client = chromadb.PersistentClient(path="./chroma_db")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_collection(name="calendar_events", embedding_function=ef)


def query_rag(collection, query, n_results=5):
    """Retrieve relevant past events for a given query"""
    results = collection.query(query_texts=[query], n_results=n_results)
    return results['documents'][0]


# ── 3. Google Calendar helpers ────────────────────────────────────────────────

def get_todays_events(service, target_date):
    """Fetch existing events for a specific date in local timezone"""
    # start and end of the target day in local time
    start = target_date.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    end   = target_date.replace(hour=23, minute=59, second=59, microsecond=0)

    # ensure timezone aware
    if start.tzinfo is None:
        start = start.replace(tzinfo=TZ)
        end   = end.replace(tzinfo=TZ)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return events_result.get('items', [])


def format_existing_events(events):
    """Convert GCal event objects into readable strings for the prompt"""
    if not events:
        return "No existing events."
    lines = []
    for e in events:
        start = e['start'].get('dateTime', e['start'].get('date', ''))
        end   = e['end'].get('dateTime',   e['end'].get('date', ''))
        try:
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt   = datetime.fromisoformat(end.replace('Z', '+00:00'))
            lines.append(f"- {e.get('summary', 'Untitled')}: "
                         f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}")
        except:
            lines.append(f"- {e.get('summary', 'Untitled')}")
    return "\n".join(lines)


# ── 4. The Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a smart personal schedule assistant.
Your job is to help the user fill their day with productive time blocks.

Rules you must follow:
- NEVER schedule events that overlap with existing events
- Respect the user's historical patterns when possible
- Always return a valid JSON array and nothing else
- No markdown, no code fences, no explanation — ONLY the raw JSON array
- Each event must have: title, start (HH:MM 24hr), end (HH:MM 24hr)
- Do not schedule before 8:00 or after 22:00 unless history suggests otherwise
- Leave at least 15 minutes between events
- Fill the ENTIRE day with time blocks, not just 1-2 events
- If the user mentions a deadline or priority, reflect that in the schedule"""


def build_prompt(goal, date_str, day_of_week, existing_events_str, rag_patterns):
    rag_str = "\n".join(f"- {p}" for p in rag_patterns)
    return f"""Today is {day_of_week}, {date_str}.

User's goal: "{goal}"

IMPORTANT: The user's goal may mention additional time constraints like work hours,
commute, appointments, or other commitments. Extract these from the goal and treat
them as FIXED BLOCKED TIME that cannot be scheduled over.

Existing events already on the calendar (DO NOT overlap these):
{existing_events_str}

Historical patterns from the user's past calendar:
{rag_str}

Instructions:
1. First identify ALL blocked time from both existing events AND the user's goal
2. Find the remaining free time blocks
3. Fill free time with varied, appropriate events (include lunch, breaks, not just work blocks)
4. Respect the user's historical patterns

Return ONLY a valid JSON array like this:
[
  {{"title": "Commute to Work", "start": "07:45", "end": "08:00"}},
  {{"title": "Work", "start": "08:00", "end": "17:00"}},
  {{"title": "Commute Home", "start": "17:00", "end": "17:15"}},
  {{"title": "Deep Work — Coding", "start": "17:30", "end": "19:30"}}
]"""


# ------ revising what u currently have
def build_revision_prompt(goal, date_str, day_of_week, existing_events_str, rag_patterns, previous_schedule, complaint):
    """Build a prompt for revising an existing schedule based on user feedback"""
    rag_str = "\n".join(f"- {p}" for p in rag_patterns)
    
    # format previous schedule for the prompt
    prev_str = "\n".join(
        f"- {e['title']}: {e['start'][11:16]} - {e['end'][11:16]}"
        for e in previous_schedule
    )

    return f"""Today is {day_of_week}, {date_str}.

User's original goal: "{goal}"

Existing events already on the calendar (DO NOT overlap these):
{existing_events_str}

Historical patterns from the user's past calendar:
{rag_str}

The previous schedule that was generated:
{prev_str}

The user is unhappy with this schedule and said:
"{complaint}"

Regenerate the ENTIRE schedule from scratch, fixing the complaint while still:
- Respecting the user's original goal
- Not overlapping existing events
- Following historical patterns where relevant

Return ONLY a valid JSON array like this:
[
  {{"title": "Deep Work — Coding", "start": "09:00", "end": "11:00"}},
  {{"title": "Lunch", "start": "12:00", "end": "13:00"}}
]"""


# ── 5. Parse & validate LLM output ───────────────────────────────────────────

def parse_events(response, target_date):
    """Extract JSON from model response and convert to GCal format"""
    # strip markdown code fences if present
    response = re.sub(r'```json|```', '', response).strip()

    # extract JSON array
    match = re.search(r'\[.*\]', response, re.DOTALL)
    if not match:
        print("Could not find JSON array in response")
        print("Raw response:", response)
        return []

    try:
        events = json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print("Raw response:", response)
        return []

    # convert HH:MM strings to full ISO datetime strings for GCal
    gcal_events = []
    date_str = target_date.strftime('%Y-%m-%d')
    for e in events:
        try:
            start_iso = f"{date_str}T{e['start']}:00"
            end_iso   = f"{date_str}T{e['end']}:00"
            gcal_events.append({
                "title": e['title'],
                "start": start_iso,
                "end":   end_iso
            })
        except KeyError as err:
            print(f"Skipping malformed event: {err}")
    return gcal_events


# ── 6. Main agent loop ────────────────────────────────────────────────────────

def run_agent(goal, target_date=None):
    if target_date is None:
        # default to tomorrow in local timezone
        now = datetime.now(TZ)
        target_date = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)

    day_of_week = target_date.strftime('%A')
    date_str    = target_date.strftime('%Y-%m-%d')

    print(f"\nAgent starting for {day_of_week} {date_str}")
    print(f"Goal: {goal}\n")

    # load everything
    model, tokenizer = load_model()
    collection       = load_rag()
    service          = get_calendar_service()

    # step 1 — fetch existing events
    print("Fetching existing events...")
    existing     = get_todays_events(service, target_date)
    existing_str = format_existing_events(existing)
    print(f"Found {len(existing)} existing events:")
    print(existing_str)

    # step 2 — query RAG for patterns
    print("Querying RAG for patterns...")
    rag_patterns = query_rag(collection, f"{day_of_week} schedule {goal}")
    print(f"Found {len(rag_patterns)} relevant patterns:")
    for p in rag_patterns:
        print(f"  → {p}")

    # step 3 — build prompt and ask model
    print("\n🧠 Asking model to build schedule...")
    prompt   = build_prompt(goal, date_str, day_of_week, existing_str, rag_patterns)
    response = ask(model, tokenizer, prompt, SYSTEM_PROMPT)
    print(f"\nModel response:\n{response}\n")

    # step 4 — parse response
    events = parse_events(response, target_date)
    if not events:
        print("No valid events parsed. Try again or adjust the prompt.")
        return

    # step 5 — confirm before writing to calendar
    print("Proposed schedule:")
    for e in events:
        print(f"  {e['start'][11:16]} - {e['end'][11:16]}  {e['title']}")

    confirm = input("\nWrite these to Google Calendar? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Cancelled.")
        return

    # step 6 — write to GCal
    print("writing to GCal...")
    for e in events:
        create_event(service, e['title'], e['start'], e['end'],
                     description="Created by Schedule Agent")
        print(f"Created: {e['title']}")

    print("Done! Check your Google Calendar.")


if __name__ == "__main__":
    goal = input("What's your goal for tomorrow? ")
    run_agent(goal)