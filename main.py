from machine import UART, Pin
import time

# UART0: MAIN TX/RX (TX = GP0, RX = GP1)
uart0 = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# UART1: PANEL RX (RX = GP5)
uart1 = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))

print("Pico UART command sender + logger started...\n")
print("Type 'timer', 'power', 'mode', 'up', 'down', or 'fan' and press Enter.\n")

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

def read_uart_burst(uart, label):
    if uart.any():
        data = bytearray()
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < 50:
            if uart.any():
                data += uart.read(uart.any())
        if data:
            if label == "MAIN -> PANEL":
                color = "\033[1;32;40m"  # Green
            else:
                color = "\033[1;31;40m"  # Red
            print(f"{color}[{label}]: {to_hex_string(data)}\033[0m")


def send_command(name):
    if name in commands:
        data = commands[name]
        uart0.write(data)
        print(f"\033[1;32;40m[SENT -> MAIN] {name.upper()}: {to_hex_string(data)}\033[0m\n")
    else:
        print(f"\033[1;33;40m[WARNING] Unknown command: {name}\033[0m\n")

# For interactive command input (via REPL/Thonny)
try:
    import sys, select
    interactive = True
except:
    interactive = False

# Main loop
while True:
    read_uart_burst(uart1, "PANEL -> MAIN")  # RED
    read_uart_burst(uart0, "MAIN -> PANEL")  # GREEN
    if interactive:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip().lower()
            send_command(cmd)

    time.sleep(0.01)

