from machine import Pin
import rp2
import time

# Constants
CYCLE_NS = 8
LOOP_CYCLES = 2
CYCLE_TO_US = (LOOP_CYCLES * CYCLE_NS) / 1000  # float for precision

START_MIN = 4490
START_MAX = 4550
END_MIN = 470
END_MAX = 520

@rp2.asm_pio()
def pulse_length():
    wait(0, pin, 0)
    mov(x, invert(null))
    label("count")
    jmp(pin, "end")
    jmp(x_dec, "count")
    label("end")
    mov(isr, invert(x))
    push()

pin = Pin(0, Pin.IN, Pin.PULL_UP)
sm = rp2.StateMachine(0, pulse_length, freq=125_000_000, in_base=pin)
sm.active(1)

def get_next_low_duration():
    while True:
        if sm.rx_fifo():
            cycles = sm.get()
            return int(cycles * CYCLE_TO_US)

while True:
    print("Waiting for start pulse...")
    while True:
        dur = get_next_low_duration()
        if START_MIN <= dur <= START_MAX:
            break

    # Record full message gaps for replay
    full_gap_list = []

    # Measure first gap after start pulse
    gap_start = time.ticks_us()

    while True:
        dur = get_next_low_duration()
        gap_end = time.ticks_us()
        gap_us = time.ticks_diff(gap_end, gap_start)
        full_gap_list.append(gap_us)

        if END_MIN <= dur <= END_MAX:
            break

        gap_start = time.ticks_us()

    # Decode from gap 3 onward
    decoded = ""
    for i, gap in enumerate(full_gap_list):
        if i < 2:
            continue  # retain for replay, but don't decode
        if 400 <= gap <= 520:
            decoded += "1"
        elif 920 <= gap <= 1020:
            decoded += "0"
        else:
            break

    print(f"Decoded: 11{decoded}")
    print(f"Raw gap timings: {full_gap_list}")

