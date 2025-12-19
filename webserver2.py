# webserver2.py
# Web status screen for the donation system

#
# How it works:
# - Main program calls log_and_print("some message")
# - This file maps that raw message to a short user-facing message
# - Flask serves a nice UI at http://<pi-ip>:5000
# - The page does NOT auto-reload (no flashing). It polls /status_json and updates text smoothly.

from flask import Flask, render_template_string, jsonify
import threading
import datetime
import re

app = Flask(__name__)

# --- Optional debug log buffer (not shown on website) ---
LOG_BUFFER = []
MAX_LOGS = 300

# --- User-facing state (what the website displays) ---
CURRENT_USER_MSG = "Welcome to Goodwill"
DONATION_TOTAL = 0

# Show "Thank you" for a short time after donation counted
LAST_DONATION_TS = None
THANK_YOU_DISPLAY_SECONDS = 5


def _add_log(message: str):
    """Store raw logs with timestamps (optional)."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    LOG_BUFFER.append((ts, message))
    if len(LOG_BUFFER) > MAX_LOGS:
        del LOG_BUFFER[:len(LOG_BUFFER) - MAX_LOGS]


def _map_to_user_message(msg: str):
    """
    Map raw program prints -> short user-facing messages.

    IMPORTANT:
    If multiple log messages happen quickly, the LAST mapped message wins.
    So only map messages that represent "the step" you want to show.
    """

    # Donation / object detection
    if msg.startswith("Object detected by distance sensors."):
        return "Donation detected"

    # PIR window
    # Your main code now prints:
    # "Checking for sustained motion for up to ..."
    if msg.startswith("Checking for sustained motion"):
        return "Detecting motion"

    if msg.startswith("No sustained motion detected. Safely opening doors."):
        return "No motion detected"

    # PIR detected (your new print starts with "Person detected (PIR HIGH for")
    if msg.startswith("Person detected (PIR HIGH"):
        return "Motion detected"

    # Door + conveyor steps
    if msg.startswith("Motors FORWARD (opening doors)"):
        return "Doors opening"

    if msg.startswith("Doors open. Starting conveyor belt"):
        return "Conveyor belt moving"

    if msg.startswith("Motors BACKWARD (closing doors)"):
        return "Doors closing"

    if msg.startswith("Conveyor belt stopped."):
        return "Conveyor belt stopped"

    if msg.startswith("Lock engaged (door locked)."):
        return "System locked"

    # Button press
    if msg.startswith("Button pressed! Measuring distance once"):
        return "System starts!"

    # Hide raw sensor lines from UI
    if msg.startswith("Sensor 1:"):
        return None

    # If motion was detected and the system stays locked
    if msg.startswith("Doors remain closed for safety."):
        return "System stays locked"

    # "No object detected" case
    if msg.startswith("No object detected. Motors, conveyor, and lock state unchanged."):
        return "No donation detected"

    # Startup line
    if msg.startswith("System ready. Waiting for button press"):
        return "Welcome to Goodwill"

    # IMPORTANT: do NOT map "Total donations so far" to status,
    # because it will overwrite other messages instantly.
    if msg.startswith("Total donations so far:"):
        return None

    # Donation counted is handled separately in log_message()
    if msg.startswith("Donation counted! Total donations:"):
        return None

    return None


def log_message(message: str):
    """
    Record raw log + update CURRENT_USER_MSG / DONATION_TOTAL for website.
    """
    global CURRENT_USER_MSG, DONATION_TOTAL, LAST_DONATION_TS

    _add_log(message)

    # Donation counted: update total + show thank-you message
    if message.startswith("Donation counted! Total donations:"):
        m = re.search(r"Total donations:\s*(\d+)", message)
        if m:
            try:
                DONATION_TOTAL = int(m.group(1))
            except ValueError:
                pass

        LAST_DONATION_TS = datetime.datetime.now()
        CURRENT_USER_MSG = "Thank you for your donation!"
        return

    # Otherwise map to a short user-facing message
    user_msg = _map_to_user_message(message)
    if user_msg is not None:
        CURRENT_USER_MSG = user_msg


def log_and_print(message: str):
    """
    Use this instead of print() in your main code.
    It prints to terminal AND updates the website.
    """
    print(message)
    log_message(message)


def get_status_state():
    """
    Compute what the website should show right now.
    (e.g., after thank-you timer, return to Welcome)
    """
    global CURRENT_USER_MSG

    now = datetime.datetime.now()
    user_message = CURRENT_USER_MSG
    header_text = "Welcome to Goodwill"

    # After donation completes, keep Thank-you for a few seconds, then revert to Welcome
    if LAST_DONATION_TS is not None and CURRENT_USER_MSG == "Thank you for your donation!":
        if (now - LAST_DONATION_TS).total_seconds() > THANK_YOU_DISPLAY_SECONDS:
            user_message = "Welcome to Goodwill"
            # NOTE: we are not changing CURRENT_USER_MSG here on purpose.
            # It's fine if the UI shows "Welcome" while the internal last msg is Thank-you.

    # Header is just a nicer “title” above the big status
    if user_message == "Thank you for your donation!":
        header_text = "Thank you!"
    elif user_message in (
        "Donation detected",
        "Detecting motion",
        "No motion detected",
        "Doors opening",
        "Conveyor belt moving",
        "Doors closing",
        "System locked",
    ):
        header_text = "Processing your donation"

    return user_message, header_text


# ---------- UI HTML (Goodwill-style) ----------
PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Goodwill Donation Box</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <style>
    :root {
      --goodwill-blue: #0053A0;
      --goodwill-blue-soft: #0a66c2;
      --cream: #fdf8f3;
      --text-main: #112132;
      --text-muted: #6b7280;
      --border-soft: #e5e7eb;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--goodwill-blue-soft);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
      color: var(--text-main);
    }

    .layout {
      width: 100%;
      max-width: 980px;
      display: flex;
      gap: 1.8rem;
      align-items: stretch;
      justify-content: center;
      flex-wrap: wrap;
    }

    .left-pane {
      flex: 0 1 320px;
      color: #ffffff;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1.2rem;
      min-height: 260px;
    }

    .title {
      font-size: 2.2rem;
      font-weight: 700;
      line-height: 1.1;
    }

    .subtitle {
      margin-top: 0.4rem;
      font-size: 0.95rem;
      opacity: 0.9;
    }

    .mascot {
      width: 100%;
      max-width: 260px;
      align-self: center;
      display: block;
      filter: drop-shadow(0 14px 25px rgba(15,23,42,0.45));
    }

    .right-card {
      flex: 1 1 360px;
      background: var(--cream);
      border-radius: 1.4rem;
      padding: 1.5rem 1.6rem 1.3rem;
      box-shadow:
        0 16px 40px rgba(15,23,42,0.25),
        0 0 0 1px rgba(15,23,42,0.09);
      display: flex;
      flex-direction: column;
      gap: 1.2rem;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    .card-title {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-main);
    }

    .badge {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      padding: 0.2rem 0.7rem;
      border-radius: 999px;
      background: #e0ecff;
      color: var(--goodwill-blue);
      border: 1px solid rgba(0, 83, 160, 0.4);
      white-space: nowrap;
    }

    .status-block {
      background: #ffffff;
      border-radius: 1rem;
      padding: 1.1rem 1rem 1rem;
      border: 1px solid var(--border-soft);
      text-align: left;
    }

    .status-label {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--text-muted);
      margin-bottom: 0.55rem;
    }

    .status-text {
      font-size: 1.6rem;
      font-weight: 650;
      line-height: 1.35;
      color: var(--text-main);
    }

    .bottom-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    .connection {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }

    .dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: #22c55e;
      box-shadow: 0 0 7px rgba(34,197,94,0.9);
    }

    .donations-pill {
      padding: 0.4rem 0.85rem;
      border-radius: 999px;
      background: #ffffff;
      border: 1px solid rgba(0, 83, 160, 0.18);
      display: inline-flex;
      align-items: baseline;
      gap: 0.35rem;
    }

    .donations-number {
      font-weight: 800;
      color: var(--goodwill-blue);
      font-size: 1rem;
    }

    @media (max-width: 780px) {
      .left-pane {
        align-items: center;
        text-align: center;
      }
      .title { font-size: 1.9rem; }
    }
  </style>

  <script>
    // No full-page reloads (no flashing).
    // We poll /status_json and update only the text.
    document.addEventListener("DOMContentLoaded", function() {
      async function refreshStatus() {
        try {
          const res = await fetch("/status_json");
          if (!res.ok) return;
          const data = await res.json();

          document.getElementById("status-text").textContent = data.user_message;
          document.getElementById("header-text").textContent = data.header_text;
          document.getElementById("donation-total").textContent = data.donation_total;
        } catch (e) {
          // ignore errors silently
        }
      }

      refreshStatus();
      setInterval(refreshStatus, 1000);
    });
  </script>
</head>
<body>
  <div class="layout">
    <div class="left-pane">
      <div>
        <div class="title">Goodwill<br>Donation Box</div>
        <div class="subtitle">Follow along as your donation makes its way safely inside.</div>
      </div>

      <!-- Put your mascot PNG at: static/goodwill_mascot.png -->
      <img src="/static/goodwill_mascot.png"
           alt="Cartoon donation box mascot"
           class="mascot">
    </div>

    <div class="right-card">
      <div class="card-header">
        <div class="card-title" id="header-text">{{ header_text }}</div>
        <span class="badge">Live status</span>
      </div>

      <div class="status-block">
        <div class="status-label">Current step</div>
        <div class="status-text" id="status-text">{{ user_message }}</div>
      </div>

      <div class="bottom-row">
        <div class="connection">
          <span class="dot"></span>
          <span>Connected to Raspberry&nbsp;Pi</span>
        </div>

        <div class="donations-pill">
          <span>Total donations:</span>
          <span class="donations-number" id="donation-total">{{ donation_total }}</span>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    user_message, header_text = get_status_state()
    return render_template_string(
        PAGE_TEMPLATE,
        user_message=user_message,
        donation_total=DONATION_TOTAL,
        header_text=header_text,
    )


@app.route("/status_json")
def status_json():
    """Small endpoint the webpage polls every second."""
    user_message, header_text = get_status_state()
    return jsonify(
        {
            "user_message": user_message,
            "header_text": header_text,
            "donation_total": DONATION_TOTAL,
        }
    )


def start_web_server(host="0.0.0.0", port=5000):
    """
    Start Flask in a background daemon thread so it doesn't block your main script.
    In your main code, call: start_web_server()
    """
    def _run():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
