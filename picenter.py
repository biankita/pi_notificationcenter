#!/usr/bin/env python3
from gpiozero import LED, Button, TonalBuzzer
import LCD1602
from signal import pause
import threading
import time
from time import sleep
from datetime import datetime
import random
import requests
import tkinter as tk
import json
from pathlib import Path


# ============================
# --- Hardware definitions ---
# ============================
led_yellow = LED(19)   # Yellow LED (GPIO19) lights on as per weekday configuration
led_blue  = LED(26)   # Blue LED (GPIO26) for weather alerts (rain)
led_red   = LED(21)   # Red LED (GPIO21) for to do items notifications received via telegram
button = Button(13, pull_up=True, bounce_time=0.25)  # 250ms debounce
tb = TonalBuzzer(17)

# ===========================================
# --- Cofiguration for Telegram messages ---
# ===========================================
last_ack_ts = 0 
last_seen_msg_id = 0   # highest Telegram message_id we've acted on
state_lock = threading.Lock()

# ============================
# --- App State / Defaults ---
# ============================
CONFIG_FILE = Path("yellow_days.json")

red_on   = False      # start off; turns ON when a Telegram message arrives
yellow_on = False     # starts off; turns ON based on weekday configuration
blue_on  = False      # starts off; turns ON base on rain probability (default >50%)

urgent_todo = "-----"  # will be replaced by Telegram message

#Random messages when todo item is cleared
messages = [
    "DANCE!!",
    "CELEBRATE!",
    "HAVE A BEER",
    "TAKE A NAP"
]

YELLOW_DAYS = set()        # 0=Mon … 6=Sun

# --- Weather config / state ---
# Longitude and Latitude for Miami, FL .  
# Longitude and Latitude for Miami, FL .  
MIAMI_LAT = 25.7617
MIAMI_LON = -80.1918

rain_prob = 0                 # latest % from API (0–100)
rain_threshold = 50           # slider will control this
WEATHER_REFRESH_SEC = 15 * 60 # auto-refresh every 15 minutes
last_weather_fetch = 0        # epoch seconds of last successful fetch


# ============================
# --- LCD helper functions ---
# ============================
def lcd_init():
    # I2C address 0x27 is common; if yours differs, change here
    LCD1602.init(0x27, 1)

def display_current_todo():
    lcd_init()
    LCD1602.write(0, 0, "To Do:") 
    LCD1602.write(1, 1, urgent_todo) 

def display_clear():
    lcd_init()
    LCD1602.write(0, 0, "Clear Schedule!") 
    LCD1602.write(1, 1, random.choice(messages)) 
    time.sleep(2)

# ============================
# --- LED control functions ---
# ============================
def update_red_led_state():
    if red_on:
        led_red.on()
    else:
        led_red.off()

def update_blue_led_state():
    if blue_on:
        led_blue.on()
    else:
        led_blue.off()

def load_yellow_days():
    global YELLOW_DAYS
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            YELLOW_DAYS = set(int(d) for d in data.get("days", []))
        except Exception:
            YELLOW_DAYS = set()
    else:
        # default example: weekends
        YELLOW_DAYS = {5, 6}

def save_yellow_days():
    try:
        CONFIG_FILE.write_text(json.dumps({"days": sorted(YELLOW_DAYS)}, indent=2))
    except Exception:
        pass

#Turn the yellow LED on/off based on YELLOW_DAYS and set yellow_on
def update_yellow_led_state():
    global yellow_on
    today = datetime.now().weekday()
    yellow_on = (today in YELLOW_DAYS)
    if today in YELLOW_DAYS:
        led_yellow.on()
    else:
        led_yellow.off()
    


def get_rain_probability_open_meteo(lat: float, lon: float):
    """Return precipitation probability (%) for the next hour using Open-Meteo."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":  lat,
            "longitude": lon,
            "hourly":    "precipitation_probability",
            "forecast_days": 1,
            "timezone": "auto",
        }
        r = requests.get(url, params=params, timeout=10)
        d = r.json()
        probs = d["hourly"]["precipitation_probability"]
        # Use the next hour’s probability (index 0 is fine for a simple board)
        return int(probs[0])
    except Exception as e:
        print("Weather fetch error:", e)
        return None


def evaluate_blue_from_rain(prob_percent: int):
    """Update blue LED (and any UI mirrors) given a rain probability (0–100)."""
    global blue_on, rain_prob
    if prob_percent is None:
        return
    rain_prob = int(prob_percent)
    blue_on = (rain_prob > rain_threshold)   # strictly more than the threshold
    update_blue_led_state()
    # If UI variables exist, keep them in sync (safe if UI not created yet)
    try:
        rain_label_var.set(f"Rain chance: {rain_prob}%")
    except NameError:
        pass


def fetch_and_update_weather():
    """Fetch rain chance and apply to blue LED; throttled by WEATHER_REFRESH_SEC."""
    global last_weather_fetch
    now = time.time()
    if now - last_weather_fetch < 2:  # avoid accidental rapid double-calls
        return
    prob = get_rain_probability_open_meteo(MIAMI_LAT, MIAMI_LON)
    if prob is not None:
        last_weather_fetch = now
        evaluate_blue_from_rain(prob)
        
# ============================
# --- Buzzer / Tunes ----------
# ============================
def play(tune):
    for note, duration in tune:
        tb.play(note)
        sleep(float(duration))
    tb.stop()

pink_panther_tune = [
    ('C#4', 0.2), ('D4', 0.2), (None, 0.2),
    ('Eb4', 0.2), ('E4', 0.2), (None, 0.6),
    ('F#4', 0.2), ('G4', 0.2), (None, 0.6),
    ('Eb4', 0.2), ('E4', 0.2), (None, 0.2),
    ('F#4', 0.2), ('G4', 0.2), (None, 0.2),
    ('C4', 0.2), ('B4', 0.2), (None, 0.2),
    ('F#4', 0.2), ('G4', 0.2), (None, 0.2),
    ('B4', 0.2), ('Bb4', 0.5), (None, 0.6),
    ('A4', 0.2), ('G4', 0.2), ('E4', 0.2),
    ('D4', 0.2), ('E4', 0.2)
]

msg_received_tune = [
      ('E5', 0.12), ('G5', 0.12), ('E5', 0.6)
]

msg_ackn_tune = [
    ('E5', 0.2), ('C5', 0.2), ('A4', 0.2),
    ('F4', 0.3), ('D4', 0.4), ('A3', 0.6), (None, 0.3)
]

# Button ACK: toggle red LED; if turning off, play sound & clear LCD
def toggle_red_led():
    """Acknowledge alert: only turn OFF (idempotent)."""
    global red_on, last_ack_ts
    with state_lock:
        if not red_on:
            # Already off; ignore bounce or extra presses
            return
        red_on = False
        last_ack_ts = time.time()   # mark when we acknowledged

    update_red_led_state()
    print("Red LED turned OFF (ACK)")
    play(msg_ackn_tune)
    display_clear()

# ============================
# --- Telegram Listener -------
# ============================
BOT_TOKEN = ""  # <-- paste your token
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"

def telegram_listener():
    global urgent_todo, red_on, last_ack_ts, last_seen_msg_id
    last_update_id = 0
    print("Telegram listener started. Waiting for messages…")

    while True:
        try:
            r = requests.get(
                f"{API_URL}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 30},
                timeout=35
            )
            data = r.json()
            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                last_update_id = update["update_id"]
                msg = update.get("message") or update.get("edited_message")
                if not msg or "text" not in msg:
                    continue

                # Telegram gives seconds since epoch in UTC
                msg_ts = msg.get("date", 0)
                text   = msg["text"].strip()
                chat_id = msg["chat"]["id"]
                mid = msg.get("message_id", 0)

                # If we acknowledged after this message’s timestamp, skip it as stale
                #with state_lock:
                #    if msg_ts <= last_ack_ts:
                #        continue
                #    urgent_todo = text
                #    red_on = True
                #    play(msg_received_tune)
                    
                with state_lock:
                    if mid <= last_seen_msg_id:
                        continue
                    if msg_ts <= last_ack_ts:
                        continue
                    
                    last_seen_msg_id = mid
                    urgent_todo = text
                    red_on = True
                        
                update_red_led_state()
                play(msg_received_tune)
                display_current_todo()
                print(f"New TODO (chat_id={chat_id}): {text}")

                # optional confirm
                try:
                    requests.post(f"{API_URL}/sendMessage",
                                  json={"chat_id": chat_id, "text": "Added ✅"},
                                  timeout=10)
                except requests.RequestException:
                    pass

            time.sleep(0.5)

        except requests.RequestException as e:
            print("Telegram network error:", e)
            time.sleep(3)
        except Exception as e:
            print("Telegram listener error:", e)
            time.sleep(3)
            
# ============================
# --- UI CONFIG-----------
# ============================
def start_ui():
    # Load yellow-day config
    load_yellow_days()
    update_yellow_led_state()

    # Tk window setup
    root = tk.Tk()
    root.title("Pi Notification Board")
    root.geometry("380x360")
    root.resizable(False, False)

    # ====== LED indicator area ======
    led_frame = tk.Frame(root, pady=10)
    led_frame.pack()

    led_canvas = {}
    led_colors = {
        "red": ("Red", lambda: red_on),
        "yellow": ("Yellow", lambda: yellow_on),
        "blue": ("Blue", lambda: blue_on),
    }

    def draw_leds():
        for name, (label, state_fn) in led_colors.items():
            c = led_canvas[name]
            c.delete("all")
            fill = label.lower() if state_fn() else "gray60"
            c.create_oval(5, 5, 35, 35, fill=fill, outline="black", width=1)

    # Create three circles
    for i, name in enumerate(led_colors):
        f = tk.Frame(led_frame)
        f.grid(row=0, column=i, padx=15)
        lbl = tk.Label(f, text=name.capitalize())
        lbl.pack()
        c = tk.Canvas(f, width=40, height=40, highlightthickness=0)
        c.pack()
        led_canvas[name] = c

    # ====== To-Do display ======
    todo_frame = tk.Frame(root)
    todo_frame.pack(pady=(5, 10))
    tk.Label(todo_frame, text="To do:", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="e", padx=(5, 3))
    todo_var = tk.StringVar()
    todo_entry = tk.Entry(todo_frame, textvariable=todo_var, width=25, font=("Arial", 12))
    todo_entry.grid(row=0, column=1)

    
    def update_todo_display():
        # Mirror whatever is on the LCD
        if red_on:
            todo_var.set(urgent_todo)
        else:
            # show random clear message instead
            import random
            todo_var.set(random.choice(messages))
            #todo_var.set(current_message)
    
    # ====== Weather status (Blue LED) ======
    tk.Label(root, text="Rain Chance (Miami, FL)", font=("Arial", 11, "bold")).pack(pady=(6, 0))
    weather_frame = tk.Frame(root, relief="groove", borderwidth=2, padx=8, pady=8)
    weather_frame.pack(fill="x", padx=8)

    # Live label that shows the latest probability
    global rain_label_var
    rain_label_var = tk.StringVar(value="Rain chance: --%")
    tk.Label(weather_frame, textvariable=rain_label_var, font=("Arial", 11))\
        .grid(row=0, column=0, sticky="w")

    def refresh_weather_now():
        fetch_and_update_weather()  # updates label + blue light

    tk.Button(weather_frame, text="Refresh", width=10, command=refresh_weather_now)\
        .grid(row=0, column=1, sticky="e", padx=(8,0))

    # ====== Blue Light Config (threshold slider) ======
    tk.Label(root, text="Blue Light Config", font=("Arial", 11, "bold")).pack(pady=(8, 0))
    blue_cfg = tk.Frame(root, relief="groove", borderwidth=2, padx=8, pady=8)
    blue_cfg.pack(fill="x", padx=8)

    tk.Label(blue_cfg, text="Turn blue ON when rain chance is above:").grid(row=0, column=0, sticky="w")
    global rain_threshold_var
    rain_threshold_var = tk.IntVar(value=rain_threshold)

    def on_threshold_change(val):
        # val arrives as a string; coerce to int
        global rain_threshold
        rain_threshold = int(float(val))
        # Re-evaluate right away using the latest downloaded probability
        evaluate_blue_from_rain(rain_prob)

    tk.Scale(
        blue_cfg,
        from_=0, to=100, orient="horizontal", length=250,
        variable=rain_threshold_var, showvalue=True,
        command=on_threshold_change
    ).grid(row=1, column=0, sticky="ew", pady=(4,0))
    
    
    
    # ====== Yellow-light config section ======
    tk.Label(root, text="Yellow Light Config", font=("Arial", 11, "bold")).pack(pady=(8, 0))
    config_frame = tk.Frame(root, relief="groove", borderwidth=2, padx=8, pady=6)
    config_frame.pack()

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    vars_by_day = []

    def on_toggle(day_idx):
        if vars_by_day[day_idx].get():
            YELLOW_DAYS.add(day_idx)
        else:
            YELLOW_DAYS.discard(day_idx)
        save_yellow_days()
        update_yellow_led_state()

    def select_all():
        for i, v in enumerate(vars_by_day):
            v.set(1)
            YELLOW_DAYS.add(i)
        save_yellow_days()
        update_yellow_led_state()

    def clear_all():
        for v in vars_by_day:
            v.set(0)
        YELLOW_DAYS.clear()
        save_yellow_days()
        update_yellow_led_state()
        
    for i, name in enumerate(day_names):
        v = tk.IntVar(value=1 if i in YELLOW_DAYS else 0)
        vars_by_day.append(v)
        cb = tk.Checkbutton(config_frame, text=name, variable=v, command=lambda d=i: on_toggle(d))
        cb.grid(row=i//4, column=i%4, sticky="w", padx=5, pady=2)

    # Buttons for select/clear all
    btn_frame = tk.Frame(config_frame)
    btn_frame.grid(row=2, column=0, columnspan=4, pady=(8, 2))
    tk.Button(btn_frame, text="Select All", width=10,
              command=select_all).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Clear All", width=10,
              command=clear_all).pack(side="left", padx=5)
        
    # ====== Close button ======
    tk.Button(root, text="Close", command=root.destroy, width=10).pack(pady=10)

    # ====== Periodic updates ======
    def refresh_old():
        update_yellow_led_state()
        draw_leds()
        update_todo_display()
        root.after(500, refresh)  # refresh every half-second
    
    def refresh():
        # Auto-refresh weather on interval
        if time.time() - last_weather_fetch > WEATHER_REFRESH_SEC:
            fetch_and_update_weather()

        update_yellow_led_state()
        draw_leds()                # redraws the 3 UI circles, including blue
        # keep rain label up to date (in case something set rain_prob elsewhere)
        try:
            rain_label_var.set(f"Rain chance: {rain_prob}%")
        except NameError:
            pass

        update_todo_display()
        root.after(500, refresh)   # refresh every half-second
        
    refresh()
    root.mainloop()
    
    
# ============================
# --- App bootstrap -----------
# ============================
def setup():
    display_current_todo()
    update_red_led_state()
    load_yellow_days()
    update_yellow_led_state()
    
    #Initial weather fetch decides blue LED & label
    fetch_and_update_weather()
# Wire button handler
button.when_pressed = toggle_red_led

# Start Telegram listener thread
t_thread = threading.Thread(target=telegram_listener, daemon=True)
t_thread.start()

# Initialize & run
setup()
print("Press the button to toggle the red LED. Yellow and blue LEDs are set by their flags.")
#pause()  # keeps main thread alive
start_ui()
