from machine import Pin
import time
from bittimings import *

from decodedmessages import messages  
# Disable pin 0 so it does not affect the voltage of what it's connected to
# Pin(0, Pin.IN)
pin = Pin(1, Pin.IN, Pin.PULL_UP)
last_state = pin.value()
last_change_time = time.ticks_us()
durations = []
collecting = False
message_start_time = 0
MESSAGE_TIMEOUT_US = 1000
    
def decode_message(symbols):
    # Remove start and end markers, keep only bits
    bits = [s for s in symbols if s in ("0", "1")]
    binary_str = ''.join(bits)
    for msg in messages:
        if msg["binary"] == binary_str:
            return msg
    return None

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
            # If 73 durations collected, force end bit
            if len(durations) == 74:
                print("=== Message Captured (74 bits, forced end) ===")
                symbols = [classify_duration(d) for d in durations[:-1]] + [" - END"]
                decoded_str = ''.join(symbols)
                if "?" in symbols:
                    print("Decoding failed")
                elif len(decoded_str) < 72:
                    print("Decoding failed, < 72 chars")
                else:
                    print("Decoded:", decoded_str)
                for idx, (d, s) in enumerate(zip(durations, symbols)):
                    if s == "?":
                        print(f"Bit {idx}: Unrecognized duration {d} us")
                decoded = decode_message(symbols)
                if decoded:
                    print("Matched message:", decoded)
                else:
                    print("No match found in known messages.")
                print("------------------------")
                collecting = False
                durations = []
            elif symbol == " - END":
                print("=== Message Captured ===")
                symbols = [classify_duration(d) for d in durations]
                decoded_str = ''.join(symbols)
                if "?" in symbols:
                    print("Decoding failed")
                elif len(decoded_str) < 72:
                    print("Decoding failed, < 72 chars")
                else:
                    print("Decoded:", decoded_str)
                # Print durations for undecoded bits
                for idx, (d, s) in enumerate(zip(durations, symbols)):
                    if s == "?":
                        print(f"Bit {idx}: Unrecognized duration {d} us")
                # Try to decode the message
                decoded = decode_message(symbols)
                if decoded:
                    print("Matched message:", decoded)
                else:
                    print("No match found in known messages.")
                print("------------------------")
                collecting = False
                durations = []

        last_change_time = now

    last_state = current_state

    # Timeout if collecting but no end bit after 1000 µs
    if collecting and time.ticks_diff(now, last_change_time) > MESSAGE_TIMEOUT_US:
        print("=== Message Captured ===")
        symbols = [classify_duration(d) for d in durations]
        decoded_str = ''.join(symbols)
        if "?" in symbols:
            print("Decoding failed")
        elif len(decoded_str) < 72:
            print("Decoding failed, < 72 chars")
        else:
            print("Decoded:", decoded_str, " - NO END DETECTED")
        # Print durations for undecoded bits
        for idx, (d, s) in enumerate(zip(durations, symbols)):
            if s == "?":
                print(f"Bit {idx}: Unrecognized duration {d} us")
        # Try to decode the message
        decoded = decode_message(symbols)
        if decoded:
            print("Matched message:", decoded)
        else:
            print("No match found in known messages.")
        print("------------------------")
        collecting = False
        durations = []

