# This script sends simulated button presses from the air conditioner's front panel to the main board via an RPI pico, and a 5v to 3.3v logic analyzer. 

from machine import Pin
import time

# Transmit pin (GPIO1)
tx = Pin(1, Pin.OUT, Pin.PULL_UP)
tx.high()  # idle state

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

# Confirm code sent after 11.2 ms
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
    print(f"Sending: {binary_string}")
    send_pulse(0, 4400)    # Start bit
    send_pulse(1, 1850)    # Gap 1
    for bit in binary_string:
        send_bit(bit)
    send_pulse(1, 300)     # Final bit
    send_pulse(0, 500)     # End bit
    tx.high()              # Idle

# --- Main Loop: Serial Command Input ---
print("Type a command name to transmit:")
print("Available: " + ", ".join(known_codes.keys()))

while True:

# #test code to repeatedly send 'timer' for diagnosing
#     send_code(known_codes["timer"])
#     time.sleep_us(11200)  # 11.2 ms delay
#     send_code(confirm_code)
#     time.sleep_ms(5000)


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


