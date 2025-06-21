from machine import Pin
import network
import socket
import time
import ure

# --- Wi-Fi Credentials ---
SSID = "YOUR_WIFI_HERE"
PASSWORD = "YOUR_WIFI_PASSWORD_HERE"

# --- Connect to Wi-Fi ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)
while not wlan.isconnected():
    time.sleep(0.5)
print("Connected, IP:", wlan.ifconfig()[0])

# --- AC Command Setup ---
tx = Pin(0, Pin.OUT)
tx.high()  # idle

known_codes = {
    "up":     "1110011111111010001101010",
    "down":   "1110011111111000101100111",
    "fan":    "1110011111111010101101011",
    "mode":   "1110011111111001101101001",
    "power":  "1110011111110111101100101",
}
confirm_code = "1110011111111111101110101"

CMD_DELAY_US = 11200
MIN_INTERVAL_MS = 50
FAN_WINDOW_S = 5

# --- State ---
state = {
    "power": False,
    "mode": "standby",
    "temperature": 22,
    "fan": "low",
    "last_fan_press": 0,
    "fan_toggle_window": False,
    "power_on_timer": None,
    "power_off_timer": None,
}
last_command_time = 0

# --- Command Sending ---
def send_pulse(val, us):
    tx.value(val)
    time.sleep_us(us)

def send_bit(bit):
    if bit == '1':
        send_pulse(1, 215)
        send_pulse(0, 215)
    else:
        send_pulse(1, 720)
        send_pulse(0, 215)

def send_code(binary):
    global last_command_time
    if time.ticks_diff(time.ticks_ms(), last_command_time) < MIN_INTERVAL_MS:
        time.sleep_ms(MIN_INTERVAL_MS)
    send_pulse(0, 4400)
    send_pulse(1, 1850)
    for bit in binary:
        send_bit(bit)
    send_pulse(1, 300)
    send_pulse(0, 500)
    tx.high()
    time.sleep_us(CMD_DELAY_US)
    send_pulse(0, 4400)
    send_pulse(1, 1850)
    for bit in confirm_code:
        send_bit(bit)
    send_pulse(1, 300)
    send_pulse(0, 500)
    tx.high()
    last_command_time = time.ticks_ms()

# --- Command Handler ---
def handle_command(cmd):
    now = time.time()
    if cmd == "power":
        state["power"] = not state["power"]
        if state["power"]:
            state["mode"] = "cool"
            state["temperature"] = 22
            state["fan"] = "low"
        else:
            state["mode"] = "standby"
            state["fan"] = "low"
        send_code(known_codes["power"])

    elif cmd.startswith("mode_"):
        target = cmd.split("_", 1)[1]
        if target == "standby":
            state["power"] = False
            state["mode"] = "standby"
            state["fan"] = "low"
            send_code(known_codes["power"])
            return

        mode_order = ["cool", "dehumidify", "fan"]
        if not state["power"]:
            state["power"] = True
            state["mode"] = "cool"
            state["temperature"] = 22
            state["fan"] = "low"
            send_code(known_codes["power"])
            time.sleep_ms(300)

        current = state["mode"]
        if current not in mode_order:
            current = "cool"

        while current != target:
            current_index = mode_order.index(current)
            current = mode_order[(current_index + 1) % len(mode_order)]
            state["mode"] = current
            if current == "dehumidify":
                state["fan"] = "low"
            send_code(known_codes["mode"])
            time.sleep_ms(300)

    elif cmd == "up" and state["mode"] == "cool":
        if state["temperature"] < 30:
            state["temperature"] += 1
            send_code(known_codes["up"])

    elif cmd == "down" and state["mode"] == "cool":
        if state["temperature"] > 16:
            state["temperature"] -= 1
            send_code(known_codes["down"])

    elif cmd == "fan" and state["mode"] in ["cool", "fan"]:
        if state["fan_toggle_window"] and now - state["last_fan_press"] <= FAN_WINDOW_S:
            state["fan"] = "high" if state["fan"] == "low" else "low"
            send_code(known_codes["fan"])
        else:
            # Press fan button twice with 100ms gap to skip window
            send_code(known_codes["fan"])
            time.sleep_ms(100)
            send_code(known_codes["fan"])
            state["fan"] = "high" if state["fan"] == "low" else "low"
            state["fan_toggle_window"] = True
        state["last_fan_press"] = now

# --- Timer Handling ---
def parse_hhmm(text):
    try:
        h, m = map(int, text.split(":"))
        return time.time() + h * 3600 + m * 60
    except:
        return None

def check_timers():
    now = time.time()
    if state["power_on_timer"] and now >= state["power_on_timer"]:
        handle_command("power")
        state["power_on_timer"] = None
    if state["power_off_timer"] and now >= state["power_off_timer"]:
        handle_command("power")
        state["power_off_timer"] = None

# --- Web Page ---
def html():
    mode_colors = {
        "standby": "background:red;color:white;",
        "cool": "background:green;color:white;",
        "dehumidify": "background:green;color:white;",
        "fan": "background:green;color:white;"
    }
    current_mode = state["mode"]
    fan_display = str(state['fan']).upper()

    return f"""<!DOCTYPE html>
<html><head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<style>
body {{ font-family: sans-serif; background: #f0f0f0; padding: 20px; }}
.container {{ background: white; padding: 20px; border-radius: 8px; max-width: 500px; margin: auto; box-shadow: 0 0 10px #aaa; }}
h2 {{ text-align: center; }}
form {{ display: inline-block; margin: 4px; }}
.grid {{ display: flex; justify-content: space-between; }}
.column {{ display: flex; flex-direction: column; gap: 10px; }}
button {{ padding: 10px 20px; font-size: 16px; }}
input[type='text'] {{ padding: 6px; width: 90px; font-size: 16px; }}
</style>
</head><body><div class=\"container\">
<h2>AC Control Panel</h2>
<p><b>Power:</b> {state['power']}</p>
<p><b>Mode:</b> {state['mode']}</p>
<p><b>Set temperature:</b> {state['temperature']} C</p>
<p><b>Fan:</b> {fan_display}</p>
<div class=\"grid\">
  <div class=\"column\">
    <form><button name=\"cmd\" value=\"mode_cool\" {'disabled' if current_mode == 'cool' else ''} style=\"{mode_colors['cool'] if current_mode == 'cool' else ''}\">Cool</button></form>
    <form><button name=\"cmd\" value=\"mode_dehumidify\" {'disabled' if current_mode == 'dehumidify' else ''} style=\"{mode_colors['dehumidify'] if current_mode == 'dehumidify' else ''}\">Dehumidify</button></form>
    <form><button name=\"cmd\" value=\"mode_fan\" {'disabled' if current_mode == 'fan' else ''} style=\"{mode_colors['fan'] if current_mode == 'fan' else ''}\">Fan</button></form>
    <form><button name=\"cmd\" value=\"mode_standby\" {'disabled' if current_mode == 'standby' else ''} style=\"{mode_colors['standby'] if current_mode == 'standby' else ''}\">Standby</button></form>
  </div>
  <div class=\"column\">
    <form><button name=\"cmd\" value=\"up\">Temp +</button></form>
    <form><button name=\"cmd\" value=\"down\">Temp -</button></form>
    <form><button name=\"cmd\" value=\"fan\">Fan: {fan_display}</button></form>
  </div>
</div>
<h3>Power-Off Timers</h3>
<form>
  <button name="off_h" value="1">OFF in 1h</button>
  <button name="off_h" value="2">2h</button>
  <button name="off_h" value="3">3h</button>
  <button name="off_h" value="5">5h</button>
</form>
</div></body></html>"""

# --- Web Server ---
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
sock = socket.socket()
sock.bind(addr)
sock.listen(1)
print("Listening on", addr)

while True:
    check_timers()
    cl, addr = sock.accept()
    req = cl.recv(1024).decode()
    match = ure.search("GET /\\?(.*?) HTTP", req)
    if match:
        params = match.group(1).split("&")
        for param in params:
            if param.startswith("cmd="):
                handle_command(param[4:])
            elif param.startswith("on="):
                ts = parse_hhmm(param[3:])
                if ts:
                    state["power_on_timer"] = ts
            elif param.startswith("off="):
                ts = parse_hhmm(param[4:])
                if ts:
                    state["power_off_timer"] = ts
            elif param.startswith("off_h="):
                try:
                    h = int(param[7:])
                    state["power_off_timer"] = time.time() + h * 3600
                except:
                    pass
    cl.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n")
    cl.send(html())
    cl.close()

