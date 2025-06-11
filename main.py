# WARNING: the uart lines of the air conditioner are 5v. To use the pico's UART connections, you need to step down to RX and step up to TX. I'm using a generic 4 Channels IIC I2C Logic Level Converter Bi-Directional Module 3.3V to 5V Shifter.
from machine import UART, Pin
import time

# Setup UARTs
uart = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))  # MAIN TX/RX
uart1 = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))  # PANEL TX/RX

print("UART reader + command sender started...\nType 'timer', 'power', 'mode', 'down', 'up', or 'fan' to send.")

# Button codes as byte arrays
commands = {
    "timer": bytes.fromhex("CE FE FE CE CE CE CE CE CE FE CE CE FE FE 0E CE FE FE CE CE CE CE CE CE FE CE CE CE 0E"),
    "power": bytes.fromhex("CE FE FE CE CE CE CE CE FE FE FE CE CE FE CE CE FE FE CE CE CE CE CE CE FE CE CE CE 0E"),
    "mode":  bytes.fromhex("CE FE FE CE CE CE CE CE CE FE CE CE CE FE CE FE FE CE CE CE CE CE CE FE CE CE CE 0E"),
    "down":  bytes.fromhex("CE FE FE CE CE CE CE CE FE CE CE CE FE CE CE FE FE CE CE CE CE CE CE FE CE CE CE 0E"),
    "up":    bytes.fromhex("CE FE FE CE CE CE CE FE CE CE CE FE CE FE 0E CE FE FE CE CE CE CE CE CE FE CE CE CE 0E"),
    "fan":   bytes.fromhex("CE FE FE CE CE CE CE CE CE FE CE CE FE FE FE CE FE FE CE CE CE CE CE CE FE CE CE CE 0E"),
}

def to_hex_string(data):
    return ' '.join(f'{b:02X}' for b in data)

# Send command by name
def send_command(name):
    cmd = commands.get(name)
    if cmd:
        uart.write(cmd)
        print(f"\033[1;32;40m[SENT -> MAIN]: {name.upper()} | {to_hex_string(cmd)}\n")
    else:
        print(f"\033[1;33;40m[WARNING] Unknown command: {name}\n")

# Allow sending commands by input
def check_input():
    try:
        import sys
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline().strip().lower()
            send_command(line)
    except:
        pass  # not interactive mode or select not supported

# Main loop
while True:
    # Log PANEL → MAIN traffic
    if uart1.any():
        data1 = uart1.read(uart1.any())
        print("\033[1;31;40m[PANEL -> MAIN]: " + to_hex_string(data1))

    # Optional: send commands interactively (only works via REPL)
    # comment out if you're running non-interactively
    try:
        import select
        check_input()
    except ImportError:
        pass

    time.sleep(0.1)
