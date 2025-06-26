from machine import Pin, Timer
import time
import _thread
import ujson
from simple import MQTTClient
import network

from decodedmessages import messages  

# --- LED Setup ---
led = Pin("LED", Pin.OUT)
led_timer = Timer()
led_state = {
    "mode": "solid",  # "solid", "slow", "fast", "double"
    "last_ac_msg": time.time(),
    "last_mqtt_cmd": 0,
    "mqtt_connected": False,
    "double_pulse_active": False,
    "double_pulse_step": 0,
}

def set_led(mode):
    led_state["mode"] = mode
    led_state["double_pulse_active"] = (mode == "double")
    led_state["double_pulse_step"] = 0

def led_update(timer):
    now = time.time()
    # Double pulse logic
    if led_state["double_pulse_active"]:
        # Double pulse: ON 100ms, OFF 100ms, ON 100ms, OFF 700ms
        step = led_state["double_pulse_step"]
        if step == 0:
            led.on()
            led_state["double_pulse_step"] = 1
            led_timer.init(mode=Timer.ONE_SHOT, period=100, callback=led_update)
        elif step == 1:
            led.off()
            led_state["double_pulse_step"] = 2
            led_timer.init(mode=Timer.ONE_SHOT, period=100, callback=led_update)
        elif step == 2:
            led.on()
            led_state["double_pulse_step"] = 3
            led_timer.init(mode=Timer.ONE_SHOT, period=100, callback=led_update)
        elif step == 3:
            led.off()
            led_state["double_pulse_step"] = 0
            led_state["double_pulse_active"] = False
            # Resume normal blinking after double pulse
            led_timer.init(mode=Timer.ONE_SHOT, period=700, callback=led_update)
        return

    # Normal status logic
    if not led_state["mqtt_connected"]:
        # Slow flash: 1s ON, 1s OFF
        led.value(not led.value())
        led_timer.init(mode=Timer.ONE_SHOT, period=1000, callback=led_update)
    elif now - led_state["last_ac_msg"] > 15:
        # Fast flash: 200ms ON, 200ms OFF
        led.value(not led.value())
        led_timer.init(mode=Timer.ONE_SHOT, period=200, callback=led_update)
    else:
        # Solid ON
        led.on()
        led_timer.init(mode=Timer.ONE_SHOT, period=1000, callback=led_update)

# Start LED status timer
led_timer.init(mode=Timer.ONE_SHOT, period=100, callback=led_update)

# --- Receiver Setup ---
rx_pin = Pin(1, Pin.IN, Pin.PULL_UP)
last_state = rx_pin.value()
last_change_time = time.ticks_us()
durations = []
collecting = False
message_start_time = 0
MESSAGE_TIMEOUT_US = 1000

# Shared variables for latest message
latest_message = None
latest_symbols = None
latest_durations = None
message_lock = _thread.allocate_lock()

# --- Sender Setup ---
tx_pin = Pin(0, Pin.OUT, Pin.PULL_UP)
tx_pin.high()  # idle state

# Known commands (excluding confirm)
known_codes = {
    "up":    "1110011111111010001101010",
    "down":  "1110011111111000101100111",
    "timer": "1110011111111000001100110",
    "fan":   "1110011111111010101101011",
    "mode":  "1110011111111001101101001",
    "sleep": "1110011111111001001101000",
    "power": "1110011111110111101100101",
}
confirm_code = "1110011111111111101110101"

def classify_duration(dur):
    if 2200 <= dur <= 2300:
        return "START - "  # Start
    elif 150 <= dur <= 300:
        return "1"
    elif 600 <= dur <= 900:
        return "0"
    elif 300 <= dur <= 600:
        return " - END"
    else:
        return "?"

def decode_message(symbols):
    # Remove start and end markers, keep only bits
    bits = [s for s in symbols if s in ("0", "1")]
    binary_str = ''.join(bits)
    for msg in messages:
        if msg["binary"] == binary_str:
            return msg
    return None

# Add a variable to track the time of the last successful decode
last_successful_decode_time = 0
IGNORE_AFTER_DECODE_US = 1  # 100 ms in microseconds

# WiFi Setup
WIFI_SSID = "WestburyWifiHorse"
WIFI_PASSWORD = "TessJames1"

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to WiFi...')
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(1)
    print('WiFi connected:', wlan.ifconfig())

connect_wifi()

# --- MQTT Setup ---
MQTT_BROKER = "test.mosquitto.org"  # Public broker for testing
MQTT_CLIENT_ID = "accontroller"
MQTT_TOPIC_MODE = "accontroller/currentmode"
MQTT_TOPIC_TEMP = "accontroller/currenttemp"
MQTT_SUB_MODE = "accontroller/setmode"
MQTT_SUB_TEMP = "accontroller/settemp"

last_requested_mode = None
last_requested_temp = None

def mqtt_callback(topic, msg):
    global last_requested_mode, last_requested_temp
    try:
        topic = topic.decode() if isinstance(topic, bytes) else topic
        payload = msg.decode().strip().lower()
        print(f"Received MQTT on {topic}: {payload}")
        set_led("double")

        if topic == MQTT_SUB_MODE:
            # Accepts "cool", "dry", "fan", or "power"
            requested_mode = payload
            last_requested_mode = requested_mode
            if requested_mode == "power":
                print("Power command received, sending power to AC.")
                send_code(known_codes["power"])
                time.sleep(0.5)
                return
            enforce_requested_state()
        elif topic == MQTT_SUB_TEMP:
            # Accepts a temperature as a string
            if payload.isdigit():
                requested_temp = int(payload)
                last_requested_temp = requested_temp
                enforce_requested_state()
            else:
                print(f"Ignoring invalid temperature payload: '{payload}'")
    except Exception as e:
        print("MQTT callback error:", e)

def enforce_requested_state():
    global last_requested_mode, last_requested_temp
    with message_lock:
        current = latest_message

    if not current:
        print("No current state available, cannot enforce requested state.")
        return

    # Handle power off
    if last_requested_mode == "power":
        print("Power command requested, sending power to AC.")
        send_code(known_codes["power"])
        time.sleep(0.5)
        return

    # If in standby, send power to turn on
    if current.get("mode", "").lower() == "standby" and last_requested_mode and last_requested_mode != "standby":
        print("Unit in standby, sending power ON.")
        send_code(known_codes["power"])
        time.sleep(0.5)
        return

    mode_cycle = ["cool", "dry", "fan"]  # Adjust as needed
    requested_mode = last_requested_mode
    current_mode = current.get("mode", "").lower()
    print(f"[enforce_requested_state] Requested: {requested_mode}, Current: {current_mode}")

    if requested_mode and requested_mode not in mode_cycle and requested_mode != "standby" and requested_mode != "power":
        print(f"Unknown requested mode: {requested_mode}")
        return

    # Only change mode if not already correct
    if requested_mode and current_mode != requested_mode:
        print(f"Current mode is '{current_mode}', changing to '{requested_mode}'")
        send_code(known_codes["mode"])
        time.sleep(0.5)
        print("Sent one mode press, will check again after next state update.")
        # Do NOT return here; let the function continue to check temperature if needed
    elif requested_mode:
        print(f"Already in requested mode: {requested_mode}")

    # Only adjust temperature if in cool mode and a temperature is requested
    if (
        last_requested_temp is not None
        and current.get("mode", "").lower() == "cool"
        and "display" in current
    ):
        try:
            display_temp = int(current["display"])
            print(f"Current display temp: {display_temp}, requested: {last_requested_temp}")
            if display_temp < last_requested_temp:
                send_code(known_codes["up"])
                time.sleep(0.5)
                print("Sent one 'up' press, will check again after next state update.")
            elif display_temp > last_requested_temp:
                send_code(known_codes["down"])
                time.sleep(0.5)
                print("Sent one 'down' press, will check again after next state update.")
            else:
                print(f"Set temperature to {last_requested_temp}")
        except Exception as e:
            print("Error adjusting temperature:", e)
    elif last_requested_temp is not None and current.get("mode", "").lower() != "cool":
        print("Settemp received, but not in cool mode. Will apply settemp when cool mode is active.")

def publish_latest_message(decoded, symbols, durations):
    if decoded is None:
        return
    # Broadcast current mode and temp
    try:
        if "mode" in decoded:
            mqtt_client.publish(MQTT_TOPIC_MODE, decoded["mode"])
        if "display" in decoded:
            mqtt_client.publish(MQTT_TOPIC_TEMP, str(decoded["display"]))
        print("Published current mode and temp to MQTT.")
    except Exception as e:
        print("MQTT publish failed:", e)
    # Update last AC message time for LED logic
    led_state["last_ac_msg"] = time.time()

# Setup MQTT client and callback
mqtt_client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
mqtt_client.set_callback(mqtt_callback)
try:
    mqtt_client.connect()
    mqtt_client.subscribe(MQTT_SUB_MODE)
    mqtt_client.subscribe(MQTT_SUB_TEMP)
    print(f"Subscribed to {MQTT_SUB_MODE} and {MQTT_SUB_TEMP}")
    led_state["mqtt_connected"] = True
    set_led("solid")
except Exception as e:
    print("MQTT connection failed:", e)
    led_state["mqtt_connected"] = False
    set_led("slow")

# --- Receiver Thread ---
def mainboard_reader():
    global last_state, last_change_time, durations, collecting, message_start_time
    global latest_message, latest_symbols, latest_durations
    global last_successful_decode_time

    while True:
        current_state = rx_pin.value()
        now = time.ticks_us()

        if current_state == 1 and last_state == 0:
            last_change_time = now  # HIGH started

        elif current_state == 0 and last_state == 1:
            pulse_us = time.ticks_diff(now, last_change_time)
            symbol = classify_duration(pulse_us)

            if not collecting:
                if symbol == "START - ":
                    collecting = True
                    message_start_time = now
                    durations = [pulse_us]
            else:
                durations.append(pulse_us)
                if symbol == " - END":
                    print("=== Message Captured ===")
                    symbols = [classify_duration(d) for d in durations]
                    print("Decoded:", ''.join(symbols))
                    for idx, (d, s) in enumerate(zip(durations, symbols)):
                        if s == "?":
                            print(f"Bit {idx}: Unrecognized duration {d} us")
                    decoded = decode_message(symbols)
                    if decoded:
                        print("Matched message:", decoded)
                        last_successful_decode_time = now
                        publish_latest_message(decoded, symbols, durations)
                    else:
                        print("No match found in known messages.")
                    print("------------------------")
                    with message_lock:
                        latest_message = decoded
                        latest_symbols = symbols
                        latest_durations = durations.copy()
                    collecting = False
                    durations = []

            last_change_time = now

        last_state = current_state

        # Timeout if collecting but no end bit after 1000 µs
        if collecting and time.ticks_diff(now, last_change_time) > MESSAGE_TIMEOUT_US:
            print("=== Message Captured ===")
            symbols = [classify_duration(d) for d in durations]
            print("Decoded:", ''.join(symbols), " - END (TIMEOUT)")
            for idx, (d, s) in enumerate(zip(durations, symbols)):
                if s == "?":
                    print(f"Bit {idx}: Unrecognized duration {d} us")
            decoded = decode_message(symbols)
            if decoded:
                print("Matched message:", decoded)
                last_successful_decode_time = now
                publish_latest_message(decoded, symbols, durations)
            else:
                print("No match found in known messages.")
            print("------------------------")
            with message_lock:
                latest_message = decoded
                latest_symbols = symbols
                latest_durations = durations.copy()
            collecting = False
            durations = []

        

# --- Sender Functions ---
def send_pulse(state, duration_us):
    tx_pin.value(state)
    time.sleep_us(duration_us)

def send_bit(bit):
    if bit == '1':
        send_pulse(1, 215)
        send_pulse(0, 215)
    elif bit == '0':
        send_pulse(1, 720)
        send_pulse(0, 215)

def send_code(binary_string):
    print(f"Sending: {binary_string}")
    send_pulse(0, 4400)    # Start bit
    send_pulse(1, 1850)    # Gap 1
    for bit in binary_string:
        send_bit(bit)
    send_pulse(1, 300)     # Final bit
    send_pulse(0, 500)     # End bit
    tx_pin.high()          # Idle

# --- Sender Thread (thread2) ---
def thread2():
    print("Type a command name to transmit:")
    print("Available: " + ", ".join(known_codes.keys()))
    while True:
        try:
            cmd = input(">> ").strip().lower()
            if cmd in known_codes:
                send_code(known_codes[cmd])
                time.sleep_us(11200)  # 11.2 ms delay
                send_code(confirm_code)
            else:
                print("Unknown command.")
        except KeyboardInterrupt:
            print("Exiting.")
            break
        except Exception as e:
            print("Error:", e)

def mqtt_connect():
    global mqtt_client
    try:
        mqtt_client.connect()
        mqtt_client.subscribe(MQTT_SUB_MODE)
        print(f"Subscribed to {MQTT_SUB_MODE}")
        mqtt_client.subscribe(MQTT_SUB_TEMP)
        print(f"Subscribed to {MQTT_SUB_TEMP}")
        led_state["mqtt_connected"] = True
        set_led("solid")
    except Exception as e:
        print("MQTT connection failed:", e)
        led_state["mqtt_connected"] = False
        set_led("slow")

mqtt_client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)
mqtt_client.set_callback(mqtt_callback)
mqtt_connect()

def mqtt_check_loop():
    while True:
        try:
            mqtt_client.check_msg()  # This will call mqtt_callback if a message arrives
            time.sleep(0.1)
        except Exception as e:
            print("MQTT check error:", e)
            led_state["mqtt_connected"] = False
            set_led("slow")
            time.sleep(1)

# --- Thread startup ---
_thread.start_new_thread(mainboard_reader, ())
mqtt_check_loop()