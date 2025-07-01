#This script reads incoming messages from the AC mainboard and decodes them.
import time
from bittimings import *
from decodedmessages import messages  
from networkconfig import *
from ahtx0 import *
from projectconfig import *
import projectconfig
import _thread
from machine import Pin

last_state = rx_pin.value()
last_change_time = time.ticks_us()
durations = []
collecting = None
message_start_time = 0

def decode_message(symbols):
    # Remove start and end markers, keep only bits
    bits = [s for s in symbols if s in ("0", "1")]
    binary_str = ''.join(bits)
    for msg in messages:
        if msg["binary"] == binary_str:
            return msg
    return None

def mainboard_reader():
    global collecting
    global last_state, last_change_time, durations, collecting, message_start_time
    global latest_symbols, latest_durations
    global last_successful_decode_time, last_button_press_time

    while True:
        current_state = rx_pin.value()
        now = time.ticks_us()

        #This code previously ignored incoming messages for 500ms after any button press. Not sure if actually required.
        # # Ignore all incoming messages for 500ms after any button press
        # if time.ticks_diff(time.ticks_ms(), last_button_press_time) < 500:
        #     last_state = current_state
        #     continue

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
                    if decoded and decoded != None:
                        last_successful_decode_time = now
                        projectconfig.latest_message = decoded
                    with projectconfig.message_lock:
                        latest_symbols = symbols
                        latest_durations = durations.copy()
                    collecting = False
                    durations = []

            last_change_time = now

        last_state = current_state

        if collecting and time.ticks_diff(now, last_change_time) > MESSAGE_TIMEOUT_US:
            symbols = [classify_duration(d) for d in durations]
            decoded = decode_message(symbols)
            if decoded and decoded != None:
                projectconfig.latest_message = decoded
                last_successful_decode_time = now
            with projectconfig.message_lock:
                projectconfig.latest_message = decoded
                latest_symbols = symbols
                latest_durations = durations.copy()
            collecting = False
            durations = []