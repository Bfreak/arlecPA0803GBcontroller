from machine import Pin
import time

tx = Pin(1, Pin.OUT)
tx.high()

def send_start():
    tx.low()
    time.sleep_us(4100) #target 4520
    tx.high()
    time.sleep_us(2250) #target 2260

def send_pulse(duration_us):
    tx.low()
    time.sleep_us(240)  # small gap between bits
    tx.high()
    time.sleep_us(duration_us)

def send_binary_message(bits):
    print("Sending:", bits)
    # Start bit
    send_start()

    # Data bits
    for b in bits:
        if b == '1':
            send_pulse(215)
        elif b == '0':
            send_pulse(710)

    # End bit
    send_pulse(600)
    print("Done")
    
send_binary_message("011011111000111010001000111111111111111111111011010111111111111110001001") 
