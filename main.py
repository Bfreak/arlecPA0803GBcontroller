# --- READ BEFORE USING --- # --- READ BEFORE USING --- # --- READ BEFORE USING --- # --- READ BEFORE USING ---
#
# Hi. I have released this under version v0.0.1 Alpha but it is still very much a work in progress.
# The pico WILL LIKELY crash at least once every other day. When it does, you will need to unplug it and plug it back in, and this means power cycling the air conditioner too, sometimes while it is running. The manufacturers do not advise doing this, so it is at your own risk.
# The code is not very well tested, and I have not yet implemented any error handling or recovery.
# But it does work! If you found it useful, please consider adding to it.
#
# Remember that you MUST fit a logic level shifter to the TX pin and RX pin, as the AC unit uses 5V logic and the pico uses 3.3V logic. 
# If you do not do this, you will likely damage your pico. the little 4 channel modules are cheap and easy to use, and you can find them on the usual e-waste generators.
# If you plan to use this to control the AC unit in a situation other than what it was designed (like I did, cooling another room from the loft) Be careful. I'm a risk taker and an idiot, and doing so is probalby not safe at all.
#
# --- READ BEFORE USING --- # --- READ BEFORE USING --- # --- READ BEFORE USING --- # --- READ BEFORE USING ---

from machine import Pin, Timer, I2C
import time
import _thread
import ujson
from umqttsimple import MQTTClient
import network
from decodedmessages import messages  
from networkconfig import *
from ahtx0 import AHT20
import projectconfig
from projectconfig import *
from mainboardreader import *


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



# removed, may still be useful
#last_button_press_time = 0  # Initialize last_button_press_time

loftTemp = AHT20(loft_i2c)
intakeTemp = AHT20(intake_i2c)

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

initialized = False
mode_command = "off"
mode_state = "off"
mode_real = "off"

temperature_command = "19.0"
temperature_state = "19.0"
current_temperature = "19.0"
temp_real = 19.0  # Default target temperature
loft_temp = "19.0"
real_temp = "19.0"
status_last_sent = ""
status_apply_start_time = 0
status_error_reported = False

# Homeassistant discovery topic for the air conditioner
def publish_discovery():
    payload = {
        "name": "Bedroom AC",
        "unique_id": "bedroom_ac_1",
        "mode_command_topic": MQTT_SUB_MODE, # Current REQUESTED mode: Mode requested by Home Assistant
        "mode_state_topic": MQTT_TOPIC_MODE, # Current mode: the mode REPORTED to Home Assistant, not the ACTUAL CURRENT mode
        "mode_real_topic": MQTT_REAL_MODE, # ACTUAL mode: the ACTUAL mode set on the AC
        "temperature_command_topic": MQTT_SUB_TEMP, # Current REQUESTED temperature: the temperature requested by Home Assistant
        "temperature_state_topic": MQTT_TOPIC_TEMP, # Current set temperature: the temperature REPORTED to Home Assistant, not the ACTUAL CURRENT temperature
        "current_temperature_topic": MQTT_REAL_TEMP, # Current AC SET temperature: the current teperature set, or reported by the AC unit
        "min_temp": 16,
        "initial": 22,
        "max_temp": 31,
        "modes": ["off", "cool", "dry", "fan_only"],
        "current_humidity_topic": MQTT_TOPIC_HUM, # Humidity reported by the AHT20 sensor in the loft
        "availability_topic": MQTT_TOPIC_AVAIL,
        "fan_modes": ["high", "low"],
        "precision": 1.0,
        "temp_step": 1,
        "off_mode_state_template": "{{ value_json }}",
        "cool_mode_state_template": "{{ value_json }}",
        "dry_mode_state_template": "{{ value if mode==dry, value_json.current_humidity_topic }}",
    }
    try:
        mqtt_client.publish(MQTT_DISCOVERY_TOPIC, ujson.dumps(payload), retain=True)
        mqtt_client.publish(MQTT_TOPIC_AVAIL, "online", retain=True)
    except Exception as e:
        print("MQTT discovery publish failed:", e)

def mqtt_callback(topic, msg):
    global mode_state, temperature_state, MQTT_BROKER, mqtt_client, initialized, mode_command, current_temperature, temperature_command, loft_temp
    try:
        topic = topic.decode() if isinstance(topic, bytes) else topic
        payload = msg.decode().strip().lower()
        if topic == MQTT_SUB_MODE:
            # receive mode change request
            mode_command = payload
            mode_state = payload
            mqtt_client.publish(MQTT_TOPIC_MODE, mode_state, retain=True)
            initialized = True
            # Publish set mode for Home Assistant state
            enforce_requested_state()
        elif topic == MQTT_SUB_TEMP:
            # Only allow temperature change in cool mode
            if mode_state == "cool":
                temperature_command = payload
                temperature_state = real_temp
                mqtt_client.publish(MQTT_TOPIC_TEMP, temperature_state, retain=True)
                enforce_requested_state()
            else:
                print(f"Ignoring temperature payload: '{payload}' in ", mode_state, " mode)")
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
    mqtt_client.publish(MQTT_TOPIC_MODE, mode_state, retain=True)
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

def publish_ha_state():
    """
    Publish the current state to Home Assistant.
    This includes the real mode and temperature, and the requested temperature.
    """
    #first publushing loft temperature and humidity, as an independent sensor
    # Publish loft temperature and humidity as separate sensors/entities for Home Assistant
    mqtt_client.publish("homeassistant/sensor/loft_temperature/state", "{:.1f}".format(loftTemp.temperature)[:4], retain=True)
    mqtt_client.publish("homeassistant/sensor/loft_humidity/state", "{:.1f}".format(loftTemp.relative_humidity)[:4], retain=True)

    global mode_real, real_temp, temperature_command, temperature_state
    try:
        # Publish the real mode and temperature
        mqtt_client.publish(MQTT_REAL_MODE, mode_real, retain=True)
        if mode_real == "cool": # in cool mode, publish the front panel temperature as the
            temperature_state = str(temp_real)
            mqtt_client.publish(MQTT_REAL_TEMP, "{:.1f}".format(intakeTemp.temperature)[:4], retain=True)
            mqtt_client.publish(MQTT_TOPIC_TEMP, temperature_state, retain=True)
        else:
            temperature_state = str(temp_real)
            mqtt_client.publish(MQTT_REAL_TEMP, temperature_state, retain=True)
            # mqtt_client.publish(MQTT_TOPIC_TEMP, "{:.1f}".format(intakeTemp.temperature)[:4], retain=True)
    except Exception as e:
        print("Error publishing state to Home Assistant:", e)

def enforce_requested_state():
    global mode_real, mode_command, mode_state, temperature_command, current_temperature, temperature_state, temp_real
    with projectconfig.message_lock:
        current = projectconfig.latest_message

    if current:
        mode_real = current.get("mode", "").lower()
        temp_real = current.get("display", "").lower()
    # If AC is in standby and a different mode is requested, send power first
    if mode_real == "off" and mode_command != "off" and initialized:
        send_code(known_codes["power"])
        print("power on request received, sending power on press")
        #here I made the decision to just put the device on high fan mode when it is turned on. I may or may not implement proper fan speed control later when I understand homeassistant templates better.
        time.sleep(1)
        send_code(known_codes["fanspeed"])
        time.sleep(1)
        send_code(known_codes["fanspeed"])
        time.sleep(20)
        enforce_requested_state()
    elif mode_real != mode_command and mode_command != "off" and initialized:
        send_code(known_codes["mode"])
        print("in incorrect mode:", mode_real)
        print("changing mode to:", mode_command)
        time.sleep(11)
        enforce_requested_state()
    elif mode_real != "off" and mode_command == "off" and initialized:
        send_code(known_codes["power"])
        mode_real = "off"
        time.sleep(5)
        print("turned off as requested")
        time.sleep(11)
        return
    elif temp_real != temperature_command and mode_command == "cool" and initialized:
        print("incorrect temp, changing from ", temp_real, "to", temperature_command)
        try:
            target_temp = float(temperature_command)
            temp_real_f = float(temp_real)
            # Calculate how many steps are needed
            steps = int(round(target_temp - temp_real_f))
            if steps > 0:
                for _ in range(steps):
                    send_code(known_codes["up"])
                    temp_real_f += 1.0
                    time.sleep(0.2)  # 200ms between presses
            elif steps < 0:
                for _ in range(abs(steps)):
                    send_code(known_codes["down"])
                    temp_real_f -= 1.0
                    time.sleep(0.2)  # 200ms between presses
            temp_real = "{:.1f}".format(temp_real_f)
        except Exception as e:
            print("Temperature adjustment error:", e)
    else:
        # If no changes are needed, just publish the state
        publish_ha_state()

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

def update_status():
    global mode_real, temp_real
    with projectconfig.message_lock:
        current = projectconfig.latest_message
        if current != None:
            mode_real = current.get("mode", "").lower()
            temp_real = current.get("display", "").lower()

_thread.start_new_thread(mainboard_reader, ())


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
        update_status()
        time.sleep(0.1)
        publish_ha_state()
        time.sleep(0.1)
        enforce_requested_state()
        time.sleep(1)

# --- Startup ---
connect_wifi()
setup_mqtt_client()
time.sleep(5)

# --- Thread startup ---
# mainboard_reader must always be in its own thread


  # Allow time for MQTT connection to stabilize and intial messages from AC to be received.

while True:
    background_loop()