# Pi Notification Board — README

A small Raspberry Pi dashboard that lights three LEDs and shows status on an I²C 1602 LCD while listening for Telegram messages and weather. It also includes a simple Tkinter desktop UI that mirrors the board state and lets you configure “yellow-day” schedules and a rain threshold.

# What it does

Red LED (GPIO21) — turns ON when a new Telegram text message arrives; pressing the button (GPIO13) acknowledges the alert, turns the red LED OFF, plays a short tune on the buzzer (GPIO17), clears the LCD, and shows a celebratory random message.

Yellow LED (GPIO19) — turns ON automatically on the weekdays you select (stored in yellow_days.json for persistence).

Blue LED (GPIO26) — turns ON when the rain probability for Miami, FL exceeds your configurable threshold (default 50%), fetched from Open-Meteo.

1602 I²C LCD — shows the current To-Do (latest Telegram message) or a “Clear Schedule!” message after you acknowledge.

Tkinter UI — shows virtual red/yellow/blue indicators, your current To-Do, live rain probability, a threshold slider, and checkboxes to pick the yellow-LED days.

# Hardware

Raspberry Pi (tested with Pi 5; any Pi with GPIO should work)

3× LEDs (red, yellow, blue) + suitable current-limit resistors (e.g., 220–330 Ω)

1× Momentary button (wired to GPIO13 with internal pull-up)

1× Tonal buzzer (works with gpiozero.TonalBuzzer on GPIO17)

1× 1602 LCD with I²C backpack (commonly at address 0x27)

Breadboard + jumper wires

# Software prerequisites
Raspberry Pi OS with I²C enabled (sudo raspi-config → Interface Options → I2C).

Python 3.

System packages:

sudo apt update sudo apt install -y python3-gpiozero python3-tk python3-pip i2c-tools

Python packages:

python3 -m pip install requests

The LCD1602 Python module used by your kit (place it next to your script or install the package supplied by your vendor).

Verify LCD address:

sudo i2cdetect -y 1

If your LCD is not 0x27, update LCD1602.init(0x27, 1) in the code.

Configuration
Telegram Bot
Create a bot with @BotFather (in Telegram) and obtain the bot token.

In the code, replace the placeholder token in:

BOT_TOKEN = "REPLACE_ME"

Security: Do not commit your token to Git. Prefer an environment variable:

import os BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

Then run:

export TELEGRAM_BOT_TOKEN=123456:abcdef... python3 app.py

# Yellow-day schedule file
On first run, the app creates/reads yellow_days.json (default: weekends {5,6}).

Use the UI checkboxes to change days; the file is saved automatically.

# Rain threshold
Default threshold is 50%. Adjust it with the slider in the UI.

Weather auto-refresh interval: every 15 minutes (button in UI to refresh now).

# How it works (quick tour)
Threads & state: A background Telegram listener thread polls getUpdates and, for each new text message, sets urgent_todo, flips red_on = True, plays a short tune, updates the LCD, and remembers the highest message_id (last_seen_msg_id) to avoid duplicates. A thread-safe state_lock protects red-LED acknowledgments.

Button ACK: Pressing the button calls toggle_red_led() which turns OFF red, plays an acknowledge tune, and shows a random “clear” message on the LCD.

Yellow logic: YELLOW_DAYS is loaded from yellow_days.json. On each UI refresh, update_yellow_led_state() compares today’s weekday and sets the physical LED and UI circle.

Blue logic: fetch_and_update_weather() calls Open-Meteo, stores rain_prob, and lights the blue LED if rain_prob > rain_threshold. The UI label is kept in sync.

UI refresh: Every 500 ms: redraws the virtual LEDs, updates the To-Do field (shows the current urgent text if red is ON; otherwise a random celebration), checks the weather refresh timer, and ensures the rain label matches rain_prob.
