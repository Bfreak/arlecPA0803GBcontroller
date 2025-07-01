#Here you can adjust specific configs for your project.
from machine import Pin, I2C
import _thread

# --- Receiver Pin --- This is the pin that receives signals from the AC mainboard, directed at the front panel.
rx_pin = Pin(1, Pin.IN, Pin.PULL_UP)

# --- intake AHT20 sensor --- It is highly suggested to add at least one, as the built in thermocouple on the AC unit isn't readable in cool mode.
intake_i2c = I2C(1, scl=Pin(19), sda=Pin(18))

# --- additional AHT20 sensor(s) --- Here you can add additional sensors if you have them. I chose to add an additional sensor in the loft where the AC unit is located.
loft_i2c = I2C(0, scl=Pin(17), sda=Pin(16))


# global vars
message_lock = _thread.allocate_lock()
latest_message = None
latest_symbols = None
latest_durations = None
MESSAGE_TIMEOUT_US = 1000