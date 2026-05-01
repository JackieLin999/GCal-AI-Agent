import gradio as gr
import json
import re
import zoneinfo
from datetime import datetime, timedelta
from agent import load_model, load_rag, get_todays_events, format_existing_events
from agent import query_rag, build_prompt, ask, parse_events, SYSTEM_PROMPT
from gcal import get_calendar_service, create_event

TZ = zoneinfo.ZoneInfo("America/Detroit")

# ── load everything once at startup ──────────────────────────────────────────
print("🚀 Loading model and RAG...")
model, tokenizer = load_model()
collection       = load_rag()
service          = get_calendar_service()
print("✅ Ready!")

# store proposed events between generate and confirm steps
proposed_events = []

# ── helper: render events as HTML calendar ────────────────────────────────────
def render_calendar(events, existing):
    """Render a visual day calendar as HTML"""
    
    # combine proposed and existing for display
    all_blocks = []
    
    for e in existing:
        start = e['start'].get('dateTime', '')
        end   = e['end'].get('dateTime', '')
        try:
            s = datetime.fromisoformat(start.replace('Z', '+00:00'))
            en = datetime.fromisoformat(end.replace('Z', '+00:00'))
            all_blocks.append({
                "title": e.get('summary', 'Untitled'),
                "start_h": s.hour + s.minute/60,
                "end_h":   en.hour + en.minute/60,
                "type": "existing"
            })
        except:
            pass

    for e in events:
        try:
            s  = datetime.fromisoformat(e['start'])
            en = datetime.fromisoformat(e['end'])
            all_blocks.append({
                "title": e['title'],
                "start_h": s.hour + s.minute/60,
                "end_h":   en.hour + en.minute/60,
                "type": "proposed"
            })
        except:
            pass

    # build HTML
    hour_height = 60  # px per hour
    start_hour  = 7
    end_hour    = 22
    total_hours = end_hour - start_hour
    total_height = total_hours * hour_height

    # hour labels
    hour_labels = ""
    for h in range(start_hour, end_hour + 1):
        top = (h - start_hour) * hour_height
        label = f"{h:02d}:00"
        hour_labels += f'<div style="position:absolute;top:{top}px;left:0;width:50px;font-size:11px;color:#888;text-align:right;padding-right:8px;">{label}</div>'
        # gridline
        hour_labels += f'<div style="position:absolute;top:{top}px;left:58px;right:0;border-top:1px solid #2a2a2a;"></div>'

    # event blocks
    event_blocks = ""
    for b in all_blocks:
        top    = (b['start_h'] - start_hour) * hour_height
        height = max((b['end_h'] - b['start_h']) * hour_height, 20)
        color  = "#1e3a5f" if b['type'] == "existing" else "#1a5c38"
        border = "#4a90d9" if b['type'] == "existing" else "#2ecc71"
        label  = "📌 " if b['type'] == "existing" else "✨ "

        # format time label
        sh = int(b['start_h'])
        sm = int((b['start_h'] % 1) * 60)
        eh = int(b['end_h'])
        em = int((b['end_h'] % 1) * 60)
        time_str = f"{sh:02d}:{sm:02d} - {eh:02d}:{em:02d}"

        event_blocks += f"""
        <div style="
            position:absolute;
            top:{top}px;
            left:60px;
            right:10px;
            height:{height}px;
            background:{color};
            border-left:3px solid {border};
            border-radius:4px;
            padding:4px 8px;
            box-sizing:border-box;
            overflow:hidden;
        ">
            <div style="font-size:12px;font-weight:bold;color:white;">{label}{b['title']}</div>
            <div style="font-size:10px;color:#aaa;">{time_str}</div>
        </div>"""

    # legend
    legend = """
    <div style="margin-bottom:12px;display:flex;gap:16px;font-size:12px;">
        <span><span style="color:#4a90d9">■</span> Existing events</span>
        <span><span style="color:#2ecc71">■</span> Proposed by agent</span>
    </div>"""

    html = f"""
    <div style="font-family:sans-serif;background:#111;padding:16px;border-radius:8px;">
        {legend}
        <div style="position:relative;height:{total_height}px;margin-left:10px;">
            {hour_labels}
            {event_blocks}
        </div>
    </div>"""
    return html


# ── agent functions for UI ────────────────────────────────────────────────────

def generate_schedule(goal, date_offset):
    """Run the agent and return calendar HTML + status"""
    global proposed_events

    if not goal.strip():
        return "<p style='color:red'>Please enter a goal first.</p>", "⚠️ No goal provided."

    # figure out target date
    now = datetime.now(TZ)
    target_date = (now + timedelta(days=int(date_offset))).replace(
        hour=0, minute=0, second=0, microsecond=0)
    day_of_week = target_date.strftime('%A')
    date_str    = target_date.strftime('%Y-%m-%d')

    # fetch existing events
    existing     = get_todays_events(service, target_date)
    existing_str = format_existing_events(existing)

    # query RAG
    rag_patterns = query_rag(collection, f"{day_of_week} schedule {goal}")

    # ask model
    prompt   = build_prompt(goal, date_str, day_of_week, existing_str, rag_patterns)
    response = ask(model, tokenizer, prompt, SYSTEM_PROMPT)

    # parse
    events = parse_events(response, target_date)
    if not events:
        return "<p style='color:red'>Could not parse schedule. Try rephrasing your goal.</p>", "❌ Failed"

    proposed_events = events

    # render calendar
    calendar_html = render_calendar(events, existing)
    status = f"✅ Generated {len(events)} events for {day_of_week} {date_str}. Click Confirm to save."
    return calendar_html, status


def confirm_schedule():
    """Write proposed events to Google Calendar"""
    global proposed_events

    if not proposed_events:
        return "⚠️ No schedule to confirm. Generate one first."

    for e in proposed_events:
        create_event(service, e['title'], e['start'], e['end'],
                     description="Created by Schedule Agent")

    count = len(proposed_events)
    proposed_events = []
    return f"🎉 {count} events added to Google Calendar!"


# ── Gradio UI ─────────────────────────────────────────────────────────────────

with gr.Blocks(theme=gr.themes.Default(), title="Schedule Agent") as app:
    gr.Markdown("# 🗓️ AI Schedule Agent")
    gr.Markdown("Describe your goal for the day and the agent will build a schedule based on your history.")

    with gr.Row():
        with gr.Column(scale=1):
            goal_input = gr.Textbox(
                label="What's your goal?",
                placeholder="e.g. I have a lot of coding to do and work from 9-5",
                lines=3
            )
            date_offset = gr.Slider(
                minimum=1, maximum=7, value=1, step=1,
                label="Days from today (1 = tomorrow)"
            )
            generate_btn = gr.Button("🧠 Generate Schedule", variant="primary")
            status_box   = gr.Textbox(label="Status", interactive=False)
            confirm_btn  = gr.Button("✅ Confirm & Save to Google Calendar", variant="secondary")
            confirm_status = gr.Textbox(label="", interactive=False)

        with gr.Column(scale=2):
            calendar_display = gr.HTML(label="Proposed Schedule")

    generate_btn.click(
        fn=generate_schedule,
        inputs=[goal_input, date_offset],
        outputs=[calendar_display, status_box]
    )
    confirm_btn.click(
        fn=confirm_schedule,
        inputs=[],
        outputs=[confirm_status]
    )

app.launch()