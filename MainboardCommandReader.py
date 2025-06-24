from machine import Pin
import time

pin = Pin(1, Pin.IN, Pin.PULL_UP)
last_state = pin.value()
last_change_time = time.ticks_us()
durations = []
collecting = False
message_start_time = 0
MESSAGE_TIMEOUT_US = 1000

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

while True:
    current_state = pin.value()
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
                print("------------------------")
                collecting = False
                durations = []

        last_change_time = now

    last_state = current_state

    # Timeout if collecting but no end bit after 1000 µs
    if collecting and time.ticks_diff(now, last_change_time) > MESSAGE_TIMEOUT_US:
                print("=== Message Captured ===")
                symbols = [classify_duration(d) for d in durations]
                print("Decoded:", ''.join(symbols), " - NO END DETECTED")
                print("------------------------")
                collecting = False
                durations = []

