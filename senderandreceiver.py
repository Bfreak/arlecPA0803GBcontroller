from machine import Pin
import time
import _thread

from decodedmessages import messages  # Import the known messages

# --- SENDER SETUP ---
tx = Pin(1, Pin.OUT, Pin.PULL_UP)
tx.high()  # idle state

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

def send_pulse(state, duration_us):
    tx.value(state)
    time.sleep_us(duration_us)

def send_bit(bit):
    if bit == '1':
        send_pulse(1, 215)
        send_pulse(0, 215)
    elif bit == '0':
        send_pulse(1, 720)
        send_pulse(0, 215)

def send_code(binary_string):
    print(f"[TX] Sending: {binary_string}")
    send_pulse(0, 4400)    # Start bit
    send_pulse(1, 1850)    # Gap 1
    for bit in binary_string:
        send_bit(bit)
    send_pulse(1, 300)     # Final bit
    send_pulse(0, 500)     # End bit
    tx.high()              # Idle

def sender_thread():
    print("Type a command name to transmit at any time.")
    print("Available: " + ", ".join(known_codes.keys()))
    while True:
        try:
            cmd = input(">> ").strip().lower()
            if cmd in known_codes:
                send_code(known_codes[cmd])
                time.sleep_us(11200)  # 11.2 ms delay
                send_code(confirm_code)
            elif cmd:
                print("Unknown command.")
        except Exception as e:
            print("Sender error:", e)

# --- RECEIVER SETUP ---
rx = Pin(0, Pin.IN, Pin.PULL_UP)
last_state = rx.value()
last_change_time = time.ticks_us()
durations = []
collecting = False
MESSAGE_TIMEOUT_US = 1000

def classify_duration(dur):
    if 4000 <= dur <= 4800:
        return "START - "  # Start
    elif 200 <= dur <= 300:
        return "1"
    elif 700 <= dur <= 800:
        return "0"
    elif 300 <= dur <= 600:
        return " - END"
    else:
        return "?"

def decode_message(symbols):
    bits = [s for s in symbols if s in ("0", "1")]
    binary_str = ''.join(bits)
    for msg in messages:
        if msg.get("binary") == binary_str:
            return msg
    return None

def receive_loop():
    global last_state, last_change_time, durations, collecting
    rx_state = rx.value()
    now = time.ticks_us()

    if rx_state == 1 and last_state == 0:
        last_change_time = now  # HIGH started

    elif rx_state == 0 and last_state == 1:
        pulse_us = time.ticks_diff(now, last_change_time)
        symbol = classify_duration(pulse_us)

        if not collecting:
            if symbol == "START - ":
                collecting = True
                durations = [pulse_us]
        else:
            durations.append(pulse_us)
            if symbol == " - END":
                print("\n[RX] === Message Captured ===")
                symbols = [classify_duration(d) for d in durations]
                print("[RX] Decoded:", ''.join(symbols))
                for idx, (d, s) in enumerate(zip(durations, symbols)):
                    if s == "?":
                        print(f"[RX] Bit {idx}: Unrecognized duration {d} us")
                decoded = decode_message(symbols)
                if decoded:
                    print("[RX] Matched message:", decoded)
                else:
                    print("[RX] No match found in known messages.")
                print("[RX] ------------------------")
                collecting = False
                durations = []

        last_change_time = now

    last_state = rx_state

    # Timeout if collecting but no end bit after 1000 µs
    if collecting and time.ticks_diff(now, last_change_time) > MESSAGE_TIMEOUT_US:
        print("\n[RX] === Message Captured ===")
        symbols = [classify_duration(d) for d in durations]
        print("[RX] Decoded:", ''.join(symbols), " - NO END DETECTED")
        for idx, (d, s) in enumerate(zip(durations, symbols)):
            if s == "?":
                print(f"[RX] Bit {idx}: Unrecognized duration {d} us")
        decoded = decode_message(symbols)
        if decoded:
            print("[RX] Matched message:", decoded)
        else:
            print("[RX] No match found in known messages.")
        print("[RX] ------------------------")
        collecting = False
        durations = []

# --- START SENDER THREAD ---
_thread.start_new_thread(sender_thread, ())

print("Listening for incoming messages...")

while True:
    receive_loop()
    time.sleep_ms(1)