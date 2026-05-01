from flask import Flask, request, jsonify
from flask_cors import CORS
import zoneinfo
from datetime import datetime, timedelta
from agent import (load_model, load_rag, get_todays_events,
                   format_existing_events, query_rag, build_prompt,
                   ask, parse_events, SYSTEM_PROMPT)
from gcal import get_calendar_service, create_event

app = Flask(__name__)
CORS(app)  # allows the Chrome extension to call this server

TZ = zoneinfo.ZoneInfo("America/Detroit")

# load everything once at startup
print("Loading model and RAG...")
model, tokenizer = load_model()
collection       = load_rag()
service          = get_calendar_service()
print("Server ready.")

# store proposed events between /generate and /confirm calls
pending_events = []


@app.route("/generate", methods=["POST"])
def generate():
    global pending_events

    data = request.json
    goal = data.get("goal", "").strip()
    date_offset = int(data.get("date_offset", 1))

    if not goal:
        return jsonify({"error": "No goal provided"}), 400

    # figure out target date
    now = datetime.now(TZ)
    target_date = (now + timedelta(days=date_offset)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    day_of_week = target_date.strftime("%A")
    date_str    = target_date.strftime("%Y-%m-%d")

    # fetch existing events
    existing = get_todays_events(service, target_date)
    existing_str = format_existing_events(existing)

    # format existing for response
    existing_formatted = []
    for e in existing:
        start = e["start"].get("dateTime", "")
        end   = e["end"].get("dateTime", "")
        try:
            s  = datetime.fromisoformat(start.replace("Z", "+00:00"))
            en = datetime.fromisoformat(end.replace("Z", "+00:00"))
            existing_formatted.append({
                "title": e.get("summary", "Untitled"),
                "start": s.strftime("%H:%M"),
                "end":   en.strftime("%H:%M"),
                "type":  "existing"
            })
        except:
            pass

    # query RAG
    rag_patterns = query_rag(collection, f"{day_of_week} schedule {goal}")

    # ask model
    prompt   = build_prompt(goal, date_str, day_of_week, existing_str, rag_patterns)
    response = ask(model, tokenizer, prompt, SYSTEM_PROMPT)

    # parse events
    events = parse_events(response, target_date)
    if not events:
        return jsonify({"error": "Could not parse schedule. Try rephrasing your goal."}), 500

    # store for confirm step
    pending_events = events

    # format proposed events for response
    proposed_formatted = []
    for e in events:
        s  = datetime.fromisoformat(e["start"])
        en = datetime.fromisoformat(e["end"])
        proposed_formatted.append({
            "title": e["title"],
            "start": s.strftime("%H:%M"),
            "end":   en.strftime("%H:%M"),
            "type":  "proposed"
        })

    return jsonify({
        "date":     f"{day_of_week}, {date_str}",
        "existing": existing_formatted,
        "proposed": proposed_formatted
    })


@app.route("/confirm", methods=["POST"])
def confirm():
    global pending_events

    if not pending_events:
        return jsonify({"error": "No pending schedule to confirm"}), 400

    for e in pending_events:
        create_event(service, e["title"], e["start"], e["end"],
                     description="Created by Schedule Agent")

    count          = len(pending_events)
    pending_events = []

    return jsonify({"message": f"{count} events added to Google Calendar."})


@app.route("/revise", methods=["POST"])
def revise():
    global pending_events

    data        = request.json
    complaint   = data.get("complaint", "").strip()
    goal        = data.get("goal", "").strip()
    date_offset = int(data.get("date_offset", 1))

    if not complaint:
        return jsonify({"error": "No complaint provided"}), 400

    if not pending_events:
        return jsonify({"error": "No existing schedule to revise"}), 400

    # figure out target date
    now         = datetime.now(TZ)
    target_date = (now + timedelta(days=date_offset)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    day_of_week = target_date.strftime("%A")
    date_str    = target_date.strftime("%Y-%m-%d")

    # fetch existing events
    existing     = get_todays_events(service, target_date)
    existing_str = format_existing_events(existing)

    # format existing for response
    existing_formatted = []
    for e in existing:
        start = e["start"].get("dateTime", "")
        end   = e["end"].get("dateTime", "")
        try:
            s  = datetime.fromisoformat(start.replace("Z", "+00:00"))
            en = datetime.fromisoformat(end.replace("Z", "+00:00"))
            existing_formatted.append({
                "title": e.get("summary", "Untitled"),
                "start": s.strftime("%H:%M"),
                "end":   en.strftime("%H:%M"),
                "type":  "existing"
            })
        except:
            pass

    # query RAG
    rag_patterns = query_rag(collection, f"{day_of_week} schedule {goal}")

    # build revision prompt
    from agent import build_revision_prompt
    prompt   = build_revision_prompt(
        goal, date_str, day_of_week, existing_str,
        rag_patterns, pending_events, complaint
    )
    response = ask(model, tokenizer, prompt, SYSTEM_PROMPT)

    # parse new events
    events = parse_events(response, target_date)
    if not events:
        return jsonify({"error": "Could not parse revised schedule. Try rephrasing."}), 500

    # replace pending events with revised version
    pending_events = events

    # format proposed events for response
    proposed_formatted = []
    for e in events:
        s  = datetime.fromisoformat(e["start"])
        en = datetime.fromisoformat(e["end"])
        proposed_formatted.append({
            "title": e["title"],
            "start": s.strftime("%H:%M"),
            "end":   en.strftime("%H:%M"),
            "type":  "proposed"
        })

    return jsonify({
        "date":     f"{day_of_week}, {date_str}",
        "existing": existing_formatted,
        "proposed": proposed_formatted
    })


@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)