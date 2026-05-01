const SERVER = "http://172.27.182.203:5000";

const goalInput   = document.getElementById("goal");
const offsetInput = document.getElementById("offset");
const dayLabel    = document.getElementById("dayLabel");
const generateBtn = document.getElementById("generateBtn");
const confirmBtn  = document.getElementById("confirmBtn");
const statusEl    = document.getElementById("status");
const calendarEl  = document.getElementById("calendar");
const calendarTitle = document.getElementById("calendarTitle");
const dayView     = document.getElementById("dayView");

// update day label as slider moves
offsetInput.addEventListener("input", () => {
  const offset = parseInt(offsetInput.value);
  const date   = new Date();
  date.setDate(date.getDate() + offset);
  dayLabel.textContent = offset === 1
    ? "Tomorrow"
    : date.toLocaleDateString("en-US", { weekday: "long" });
});

function setStatus(msg, type = "") {
  statusEl.textContent    = msg;
  statusEl.className      = "status " + type;
}

function renderCalendar(existing, proposed, dateStr) {
  calendarTitle.textContent = dateStr;
  dayView.innerHTML = "";

  const START_HOUR = 7;
  const END_HOUR   = 22;
  const PX_PER_HR  = 48;

  // draw hour rows
  for (let h = START_HOUR; h <= END_HOUR; h++) {
    const row = document.createElement("div");
    row.className = "hour-row";

    const label = document.createElement("div");
    label.className   = "hour-label";
    label.textContent = `${h.toString().padStart(2,"0")}:00`;
    row.appendChild(label);
    dayView.appendChild(row);
  }

  // draw events
  const allEvents = [
    ...existing.map(e => ({ ...e, type: "existing" })),
    ...proposed.map(e => ({ ...e, type: "proposed" }))
  ];

  allEvents.forEach(e => {
    const [sh, sm] = e.start.split(":").map(Number);
    const [eh, em] = e.end.split(":").map(Number);

    const startFrac = sh + sm / 60;
    const endFrac   = eh + em / 60;

    const top    = (startFrac - START_HOUR) * PX_PER_HR;
    const height = Math.max((endFrac - startFrac) * PX_PER_HR, 18);

    const block = document.createElement("div");
    block.className = `event-block ${e.type}`;
    block.style.top    = `${top}px`;
    block.style.height = `${height}px`;

    block.innerHTML = `
      <div class="event-title">${e.title}</div>
      <div class="event-time">${e.start} - ${e.end}</div>
    `;

    dayView.appendChild(block);
  });

  calendarEl.style.display = "block";
}

// generate schedule
generateBtn.addEventListener("click", async () => {
  const goal = goalInput.value.trim();
  if (!goal) { setStatus("Please enter a goal.", "error"); return; }

  generateBtn.disabled  = true;
  confirmBtn.style.display = "none";
  calendarEl.style.display = "none";
  setStatus("Generating schedule...");

  try {
    const res  = await fetch(`${SERVER}/generate`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ goal, date_offset: parseInt(offsetInput.value) })
    });
    const data = await res.json();

    if (!res.ok) { setStatus(data.error || "Error generating schedule.", "error"); return; }

    renderCalendar(data.existing, data.proposed, data.date);
    confirmBtn.style.display = "block";
    setStatus(`${data.proposed.length} events proposed.`, "success");

  } catch (err) {
    setStatus("Could not reach server. Is it running?", "error");
  } finally {
    generateBtn.disabled = false;
  }
});

// confirm and save
confirmBtn.addEventListener("click", async () => {
  confirmBtn.disabled = true;
  setStatus("Saving to Google Calendar...");

  try {
    const res  = await fetch(`${SERVER}/confirm`, { method: "POST" });
    const data = await res.json();

    if (!res.ok) { setStatus(data.error || "Error saving.", "error"); return; }

    setStatus(data.message, "success");
    confirmBtn.style.display = "none";

  } catch (err) {
    setStatus("Could not reach server.", "error");
  } finally {
    confirmBtn.disabled = false;
  }
});