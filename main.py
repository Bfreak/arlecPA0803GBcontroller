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
    "fan_only":   "1110011111111010101101011",
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



last_requested_mode = None
last_requested_temp = None

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
        "mode_command_topic": MQTT_SUB_MODE,
        "mode_state_topic": MQTT_SUB_MODE,  # <-- Home Assistant should read status from setmode
        "temperature_command_topic": MQTT_SUB_TEMP,
        "temperature_state_topic": MQTT_TOPIC_TEMP,
        "min_temp": 16,
        "max_temp": 31,
        "modes": ["off", "cool", "dry", "fan_only"],
        "current_temperature_topic": MQTT_TOPIC_TEMP,
        "availability_topic": MQTT_TOPIC_AVAIL,
        "precision": 1.0,
        "temp_step": 1,
        "temp_command_template": "{{ value if hvac_mode == 'cool' else none }}",  # Only allow temp in cool mode (for HA template support)
    }
    try:
        mqtt_client.publish(MQTT_DISCOVERY_TOPIC, ujson.dumps(payload), retain=True)
        mqtt_client.publish(MQTT_TOPIC_AVAIL, "online", retain=True)
    except Exception as e:
        print("MQTT discovery publish failed:", e)

def mqtt_callback(topic, msg):
    global last_requested_mode, last_requested_temp, MQTT_BROKER, mqtt_client
    try:
        topic = topic.decode() if isinstance(topic, bytes) else topic
        payload = msg.decode().strip().lower()
        print(f"Received MQTT on {topic}: {payload}")
        set_led("double")

        if topic == MQTT_SUB_MODE:
            # Accepts "cool", "dry", "fan_only", "off", or "power"
            requested_mode = payload
            if requested_mode == "off":
                last_requested_mode = "standby"
            else:
                last_requested_mode = requested_mode
            # Publish set mode for Home Assistant state
            mqtt_client.publish(MQTT_SUB_MODE, requested_mode, retain=True)
            if requested_mode in ["power", "off"]:
                print("Power/off command received, sending power to AC.")
                send_code(known_codes["power"])
                time.sleep(0.5)
                return
            enforce_requested_state()
        elif topic == MQTT_SUB_TEMP:
            # Only allow temperature change in cool mode
            if last_requested_mode == "cool" and payload.isdigit():
                requested_temp = int(payload)
                last_requested_temp = requested_temp
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
        if mode:
            ha_mode = "off" if mode.lower() == "standby" else mode.lower()
            mqtt_client.publish(MQTT_TOPIC_MODE, ha_mode, retain=True)
        if "display" in decoded:
            try:
                temp = int(decoded["display"])
                if 16 <= temp <= 31:
                    mqtt_client.publish(MQTT_TOPIC_TEMP, str(temp), retain=True)
            except Exception:
                pass  # Ignore invalid temperature values
    except Exception as e:
        print("MQTT publish failed:", e)
    led_state["last_ac_msg"] = time.time()
    enforce_requested_state()

def enforce_requested_state():
    """
    Ensures the requested mode and temperature are sent to the AC if needed.
    Handles standby (off) as a special case for Home Assistant.
    """
    global last_requested_mode, last_requested_temp, latest_message
    with message_lock:
        current = latest_message

    # Map 'off' to 'standby' for internal logic
    requested_mode = last_requested_mode
    if requested_mode == "off":
        requested_mode = "standby"

    current_mode = (current.get("mode", "").lower() if current else None)

    # If AC is in standby and a different mode is requested, send power first
    if current_mode == "standby" and requested_mode and requested_mode != "standby":
        send_code(known_codes["power"])
        time.sleep(0.5)
        send_code(confirm_code)
        # After turning on, must send the initial mode (if not 'cool')
        if requested_mode in ["cool", "dry", "fan_only"]:
            # If not cool, send mode/fan_only as needed
            if requested_mode == "fan_only":
                send_code(known_codes["fan_only"])
            else:
                send_code(known_codes["mode"])
            time.sleep(0.5)
            send_code(confirm_code)
        return

    # If mode does not match and not in standby, change mode
    if requested_mode and current_mode and current_mode != requested_mode and current_mode != "standby":
        mode_map = {
            "cool": "mode",
            "dry": "mode",
            "fan_only": "mode",
        }
        cmd = mode_map.get(requested_mode, None)
        if cmd and cmd in known_codes:
            send_code(known_codes[cmd])
            time.sleep(0.5)
            send_code(confirm_code)

    # Handle temperature adjustment only in cool mode
    if (
        last_requested_temp is not None
        and current
        and "display" in current
        and current.get("mode", "").lower() == "cool"
    ):
        try:
            current_temp = int(current["display"])
        except Exception:
            return  # Invalid temp, skip
        if 16 <= current_temp <= 31:
            # To change temperature, send the up/down command as needed
            while current_temp < last_requested_temp:
                send_code(known_codes["up"])
                time.sleep(0.5)
                send_code(confirm_code)
                current_temp += 1
            while current_temp > last_requested_temp:
                send_code(known_codes["down"])
                time.sleep(0.5)
                send_code(confirm_code)
                current_temp -= 1

def status_check_loop():
    global status_apply_start_time, status_error_reported
    while True:
        now = time.time()
        with message_lock:
            current = latest_message
        # Check if we have a set mode/temp
        if last_requested_mode or last_requested_temp:
            # Check if we have a recent AC message
            time_since_ac = now - led_state["last_ac_msg"]
            mode_ok = (last_requested_mode is None or (current and current.get("mode", "").lower() == last_requested_mode))
            temp_ok = (last_requested_temp is None or (current and "display" in current and int(current["display"]) == last_requested_temp))
            if time_since_ac > 30:
                h = int(time_since_ac // 3600)
                m = int((time_since_ac % 3600) // 60)
                s = int(time_since_ac % 60)
                publish_status(f"Error: No status messages for [{h:02}:{m:02}:{s:02}]")
                status_apply_start_time = 0
                status_error_reported = False
            elif mode_ok and temp_ok:
                publish_status("Settings applied")
                status_apply_start_time = 0
                status_error_reported = False
            else:
                if status_apply_start_time == 0:
                    status_apply_start_time = now
                    status_error_reported = False
                publish_status("Applying settings...")
                if not status_error_reported and (now - status_apply_start_time) > 60:
                    publish_status("Error: Button presses not functioning")
                    status_error_reported = True
        else:
            time_since_ac = now - led_state["last_ac_msg"]
            if time_since_ac > 30:
                h = int(time_since_ac // 3600)
                m = int((time_since_ac % 3600) // 60)
                s = int(time_since_ac % 60)
                publish_status(f"Error: No status messages for [{h:02}:{m:02}:{s:02}]")
                status_apply_start_time = 0
                status_error_reported = False
            else:
                publish_status("Settings applied")
                status_apply_start_time = 0
                status_error_reported = False
        time.sleep(2)



def mainboard_reader():
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

        # Timeout if collecting but no end bit after 1000 µs
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
publish_discovery()

# --- Thread startup ---
# mainboard_reader must always be in its own thread
_thread.start_new_thread(mainboard_reader, ())

def background_loop():
    # This loop will handle both status_check_loop and mqtt_check_loop
    status_last_run = 0
    while True:
        now = time.time()
        # Run status_check_loop logic every 2 seconds
        if now - status_last_run > 2:
            status_check_loop_step()
            status_last_run = now
        # Run mqtt_check_loop logic as often as possible
        try:
            mqtt_client.check_msg()
        except Exception as e:
            print("MQTT check error:", e)
            led_state["mqtt_connected"] = False
            set_led("slow")
            time.sleep(1)
        time.sleep(0.1)

def status_check_loop_step():
    global status_apply_start_time, status_error_reported
    now = time.time()
    with message_lock:
        current = latest_message
    # Check if we have a set mode/temp
    if last_requested_mode or last_requested_temp:
        # Check if we have a recent AC message
        time_since_ac = now - led_state["last_ac_msg"]
        mode_ok = (last_requested_mode is None or (current and current.get("mode", "").lower() == last_requested_mode))
        temp_ok = (last_requested_temp is None or (current and "display" in current and int(current["display"]) == last_requested_temp))
        if time_since_ac > 30:
            h = int(time_since_ac // 3600)
            m = int((time_since_ac % 3600) // 60)
            s = int(time_since_ac % 60)
            publish_status(f"Error: No status messages for [{h:02}:{m:02}:{s:02}]")
            status_apply_start_time = 0
            status_error_reported = False
        elif mode_ok and temp_ok:
            publish_status("Settings applied")
            status_apply_start_time = 0
            status_error_reported = False
        else:
            if status_apply_start_time == 0:
                status_apply_start_time = now
                status_error_reported = False
            publish_status("Applying settings...")
            if not status_error_reported and (now - status_apply_start_time) > 60:
                publish_status("Error: Button presses not functioning")
                status_error_reported = True
    else:
        time_since_ac = now - led_state["last_ac_msg"]
        if time_since_ac > 30:
            h = int(time_since_ac // 3600)
            m = int((time_since_ac % 3600) // 60)
            s = int(time_since_ac % 60)
            publish_status(f"Error: No status messages for [{h:02}:{m:02}:{s:02}]")
            status_apply_start_time = 0
            status_error_reported = False
        else:
            publish_status("Settings applied")
            status_apply_start_time = 0
            status_error_reported = False

# Start the combined background loop in the main thread (or another thread if needed)
background_loop()