from machine import Pin
import time
import _thread

from decodedmessages import messages  

# --- Receiver Setup ---
rx_pin = Pin(0, Pin.IN, Pin.PULL_UP)
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
tx_pin = Pin(1, Pin.OUT, Pin.PULL_UP)
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
    elif 200 <= dur <= 300:
        return "1"
    elif 700 <= dur <= 800:
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
IGNORE_AFTER_DECODE_US = 1_000_000  # 100 ms in microseconds

# --- Receiver Thread ---
def mainboard_reader():
    global last_state, last_change_time, durations, collecting, message_start_time
    global latest_message, latest_symbols, latest_durations
    global last_successful_decode_time

    while True:
        current_state = rx_pin.value()
        now = time.ticks_us()

        # Ignore input for 100ms after a successful decode
        if time.ticks_diff(now, last_successful_decode_time) < IGNORE_AFTER_DECODE_US:
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
                    print("=== Message Captured ===")
                    symbols = [classify_duration(d) for d in durations]
                    print("Decoded:", ''.join(symbols))
                    for idx, (d, s) in enumerate(zip(durations, symbols)):
                        if s == "?":
                            print(f"Bit {idx}: Unrecognized duration {d} us")
                    decoded = decode_message(symbols)
                    if decoded:
                        print("Matched message:", decoded)
                        last_successful_decode_time = now  # Set ignore window
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
            print("Decoded:", ''.join(symbols), " - NO END DETECTED")
            for idx, (d, s) in enumerate(zip(durations, symbols)):
                if s == "?":
                    print(f"Bit {idx}: Unrecognized duration {d} us")
            decoded = decode_message(symbols)
            if decoded:
                print("Matched message:", decoded)
                last_successful_decode_time = now  # Set ignore window even if no end but matched
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

# Start both threads
_thread.start_new_thread(mainboard_reader, ())
thread2()