from machine import Pin, Timer
import time
import _thread
import ujson
from bittimings import *
from umqttsimple import MQTTClient
import network
from decodedmessages import messages  
from network_config import *

# --- LED Setup ---
led = Pin("LED", Pin.OUT)
led_timer = Timer() # type: ignore
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
collecting = None
message_start_time = 0
MESSAGE_TIMEOUT_US = 1000
last_button_press_time = 0  # Initialize last_button_press_time

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
    "fanspeed":   "1110011111111010101101011",
    "mode":  "1110011111111001101101001",
    "sleep": "1110011111111001001101000",
    "power": "1110011111110111101100101",
}
confirm_code = "1110011111111111101110101"

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
IGNORE_AFTER_DECODE_US = 1  # 100 ms in microseconds"

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

initialized = False
reported_mode = "off"
real_mode = "off"
real_temp = "19.0"
requested_temp = "19.0"
requested_mode = "off"

status_last_sent = ""
status_apply_start_time = 0
status_error_reported = False

def publish_status(message):
    global status_last_sent
    if message != status_last_sent:
        try:
            mqtt_client.publish(MQTT_TOPIC_STATUS, message, retain=True)
            status_last_sent = message
        except Exception as e:
            print("MQTT status publish failed:", e)

def publish_discovery():
    payload = {
        "name": "Bedroom AC",
        "unique_id": "bedroom_ac_1",
        "mode_command_topic": MQTT_SUB_MODE, # Current REQUESTED mode: Mode requested by Home Assistant
        "mode_state_topic": MQTT_TOPIC_MODE, # Current mode: The mode the AC is ACTUALLY IN
        "temperature_command_topic": MQTT_SUB_TEMP,
        "temperature_state_topic": MQTT_TOPIC_TEMP,
        "min_temp": 16,
        "max_temp": 31,
        "modes": ["off", "cool", "dry", "fan_only"],
        "current_temperature_topic": MQTT_TOPIC_TEMP,
        "availability_topic": MQTT_TOPIC_AVAIL,
        "precision": 1.0,
        "temp_step": 1,
        "temperature_state_template": "{{ value }}",
    }
    try:
        mqtt_client.publish(MQTT_DISCOVERY_TOPIC, ujson.dumps(payload), retain=True)
        mqtt_client.publish(MQTT_TOPIC_AVAIL, "online", retain=True)
    except Exception as e:
        print("MQTT discovery publish failed:", e)

def mqtt_callback(topic, msg):
    global reported_mode, requested_temp, MQTT_BROKER, mqtt_client, initialized, requested_mode, reported_temp
    try:
        topic = topic.decode() if isinstance(topic, bytes) else topic
        payload = msg.decode().strip().lower()
        set_led("double")
        print("mqtt_callback triggered:", payload)
        if topic == MQTT_SUB_MODE:
            # receive mode change request
            requested_mode = payload
            reported_mode = requested_mode
            initialized = True
            # Publish set mode for Home Assistant state
            mqtt_client.publish(MQTT_TOPIC_MODE, reported_mode, retain=True)
            enforce_requested_state()
        elif topic == MQTT_SUB_TEMP:
            # Only allow temperature change in cool mode
            if reported_mode == "cool" and payload.isdigit():
                requested_temp = int(payload)
                reported_temp = requested_temp
                enforce_requested_state()
            else:
                print(f"Ignoring temperature payload: '{payload}' (not in cool mode)")
        elif topic == MQTT_SUB_NEW_BROKER:
            # Listen for new MQTT broker IP
            if payload:
                print(f"Switching MQTT broker to {payload}")
                try:
                    mqtt_client.disconnect()
                except Exception:
                    pass
                MQTT_BROKER = payload
                setup_mqtt_client()
    except Exception as e:
        print("MQTT callback error:", e)

def setup_mqtt_client():
    global mqtt_client
    mqtt_client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT, user = MQTT_username, password = MQTT_password)
    mqtt_client.set_callback(mqtt_callback)
    mqtt_connect()
    mqtt_client.publish(MQTT_TOPIC_MODE, reported_mode, retain=True)
    publish_discovery()

def mqtt_connect():
    try:
        mqtt_client.connect()
        mqtt_client.subscribe(MQTT_SUB_MODE)
        mqtt_client.subscribe(MQTT_SUB_TEMP)
        mqtt_client.subscribe(MQTT_SUB_NEW_BROKER)
        print(f"Subscribed to {MQTT_SUB_MODE}, {MQTT_SUB_TEMP}, {MQTT_SUB_NEW_BROKER}")
        led_state["mqtt_connected"] = True
        set_led("solid")
        mqtt_client.publish(MQTT_TOPIC_AVAIL, "online", retain=True)
    except Exception as e:
        print("MQTT connection failed:", e)
        led_state["mqtt_connected"] = False
        set_led("slow")

def publish_latest_message(decoded, symbols, durations):
    if decoded is None:
        return
    try:
        # Map 'standby' to 'off' for Home Assistant
        mode = decoded.get("mode")
        temp = decoded.get("display")
        if mode == "off":
            mqtt_client.publish(MQTT_REAL_MODE, "off", retain=True)
            mqtt_client.publish(MQTT_TOPIC_TEMP, temp, retain=True)
        # Publish real temperature for AH to use on dashboard
        if mode == "cool":
            mqtt_client.publish(MQTT_REAL_MODE, mode, retain=True)
            mqtt_client.publish(MQTT_REAL_TEMP, temp, retain=True)
        # Publish real mode and temp, NOT used by Home Assistant, but for debugging via mqtt
        if mode == "dry":
            mqtt_client.publish(MQTT_REAL_MODE, mode, retain=True)
            mqtt_client.publish(MQTT_REAL_TEMP, "N/A", retain=True)
        # Publish real mode and temp for dry mode, NOT used by Home Assistant, but for debugging via mqtt
        if mode == "fan_only":
            mqtt_client.publish(MQTT_REAL_MODE, mode, retain=True)
            mqtt_client.publish(MQTT_REAL_TEMP, "N/A", retain=True)
        # Publish real mode and temp for fan_only mode, NOT used by Home Assistant, but for debugging via mqtt
    except Exception as e:
        print("MQTT publish failed:", e)
    led_state["last_ac_msg"] = time.time()

def publish_ha_state():
    """
    Publish the current state to Home Assistant.
    This includes the real mode and temperature, and the requested temperature.
    """
    global real_mode, real_temp, requested_temp, reported_temp
    try:
        # Publish the real mode and temperature
        mqtt_client.publish(MQTT_REAL_MODE, real_mode, retain=True)
        if real_mode == "cool":
            mqtt_client.publish(MQTT_REAL_TEMP, real_temp, retain=True)
        # Also publish the requested temperature for reference
        mqtt_client.publish(MQTT_TOPIC_TEMP, requested_temp, retain=True)
    except Exception as e:
        print("Error publishing state to Home Assistant:", e)

def enforce_requested_state():
    """
    Ensures the requested mode and temperature are sent to the AC if needed.
    Handles standby (off) as a special case for Home Assistant.
    """
    global reported_mode, requested_temp, latest_message, requested_mode, real_mode, real_temp
    with message_lock:
        current = latest_message

    # Debug print to trace values
    print("DEBUG: enforce_requested_state called with real_mode =", real_mode, "requested_mode =", requested_mode, "initialized =", initialized)

    # Guard clause to skip enforcement if requested_mode is None
    if requested_mode is None:
        print("DEBUG: requested_mode is None, skipping enforcement")
        return

    if current:
        real_mode = current.get("mode", "").lower()
    # If AC is in standby and a different mode is requested, send power first
    if real_mode == "off" and requested_mode != "off" and initialized:
        send_code(known_codes["power"])
        print("power on request received, sending power on press")
        time.sleep(11)
        enforce_requested_state()
    elif real_mode != requested_mode and requested_mode != "off" and initialized:
        send_code(known_codes["mode"])
        print("in incorrect mode:", real_mode)
        print("changing mode to:", requested_mode)
        time.sleep(11)
        enforce_requested_state()
    elif real_mode != "off" and requested_mode == "off" and initialized:
        send_code(known_codes["power"])
        real_mode = "off"
        time.sleep(5)
        print("turned off as requested")
        time.sleep(11)
        return
    else:
        print("mode is correct, no change needed")
        time.sleep(11)
        return

    # Handle temperature adjustment only in cool mode
    if (
        requested_temp is not None
        and current
        and "display" in current
        and current.get("mode", "").lower() == "cool"
    ):
        try:
            real_temp = int(current["display"])
        except Exception:
            return  # Invalid temp, skip
        if 16.0 <= real_temp <= 31.0:
            print("incorrect temp, changing from ", real_temp, "to", requested_temp)
            target_temp = int(requested_temp)
            while real_temp < target_temp:
                send_code(known_codes["up"])
                real_temp += 1
            while real_temp > target_temp:
                send_code(known_codes["down"])
                real_temp -= 1

def mainboard_reader():
    global collecting
    global last_state, last_change_time, durations, collecting, message_start_time
    global latest_message, latest_symbols, latest_durations
    global last_successful_decode_time, last_button_press_time

    while True:
        current_state = rx_pin.value()
        now = time.ticks_us()

        # Ignore all incoming messages for 500ms after any button press
        if time.ticks_diff(time.ticks_ms(), last_button_press_time) < 500:
            last_state = current_state
            continue

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
                    symbols = [classify_duration(d) for d in durations]
                    decoded = decode_message(symbols)
                    if decoded:
                        last_successful_decode_time = now
                        publish_latest_message(decoded, symbols, durations)
                    with message_lock:
                        latest_message = decoded
                        latest_symbols = symbols
                        latest_durations = durations.copy()
                    collecting = False
                    durations = []

            last_change_time = now

        last_state = current_state

        if collecting and time.ticks_diff(now, last_change_time) > MESSAGE_TIMEOUT_US:
            symbols = [classify_duration(d) for d in durations]
            decoded = decode_message(symbols)
            if decoded:
                last_successful_decode_time = now
                publish_latest_message(decoded, symbols, durations)
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
    send_pulse(0, 4400)    # Start bit
    send_pulse(1, 1850)    # Gap 1
    for bit in binary_string:
        send_bit(bit)
    send_pulse(1, 300)     # Final bit
    send_pulse(0, 500)     # End bit
    tx_pin.high()          # Idle
    time.sleep_us(11200)
    send_pulse(0, 4400)    # Start bit
    send_pulse(1, 1850)    # Gap 1
    for bit in "confirm_code":
        send_bit(bit)
    send_pulse(1, 300)     # Final bit
    send_pulse(0, 500)     # End bit
    tx_pin.high() 

# --- Sender Thread (thread2) ---
def thread2():
    print("Type a command name to transmit:")
    print("Available: " + ", ".join(known_codes.keys()))
    while True:
        try:
            cmd = input(">> ").strip().lower()
            if cmd in known_codes:
                send_code(known_codes[cmd])
            else:
                print("Unknown command.")
        except KeyboardInterrupt:
            print("Exiting.")
            break
        except Exception as e:
            print("Error:", e)

mqtt_client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
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


# --- Startup ---
setup_mqtt_client()

def background_loop():
    # This loop will handle both check and enforce MQTT messages
    status_last_run = 0
    while True:
        try:
            mqtt_client.check_msg()
        except Exception as e:
            print("MQTT check error:", e)
            led_state["mqtt_connected"] = False
            set_led("slow")
            time.sleep(0.1)
        time.sleep(0.1)
        enforce_requested_state()
        time.sleep(1)

# --- Thread startup ---
# mainboard_reader must always be in its own thread
_thread.start_new_thread(mainboard_reader, ())

time.sleep(5)  # Allow time for MQTT connection to stabilize and intial messages from AC to be received.

while True:
    background_loop()