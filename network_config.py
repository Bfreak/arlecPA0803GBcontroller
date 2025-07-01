# add your wifi and MQTT credentials here
WIFI_SSID = "your_wifi_ssid"
WIFI_PASSWORD = "your_wifi_password"

MQTT_username = "your_mqtt_username"  # usually "admin" for Home Assistant
MQTT_password = "your_mqtt_password"  # usually "password" for Home Assistant
MQTT_BROKER = "your_mqtt_broker"  # or use the IP address of your MQTT broker
MQTT_PORT = 1883
MQTT_CLIENT_ID = "ACcontroller"
# mode topics
MQTT_SUB_MODE = "homeassistant/accontroller/mode_command_topic" # receives requested mode from HA
MQTT_TOPIC_MODE = "homeassistant/accontroller/mode_state_topic" # mode reported to Home Assistant
# REAL MODE not used by HA, for internal use only
MQTT_REAL_MODE = "homeassistant/accontroller/mode_real_topic" # mode actually set on the AC
# temp topics
MQTT_SUB_TEMP = "homeassistant/accontroller/requested_temp" # SET temperature requested by Home Assistant
MQTT_TOPIC_TEMP = "homeassistant/accontroller/temperature_state_topic" # SET temperature reported to Home Assistant
# REAL TEMP not used by HA, for internal use only
MQTT_REAL_TEMP = "homeassistant/accontroller/real_temp" # Current ACTUAL temperature: temperature read from AHT20 on intake
# humidity topics
MQTT_TOPIC_HUM = "homeassistant/accontroller/intake_humidity" # humidity reported to Home Assistant
MQTT_TOPIC_STATUS = "homeassistant/accontroller/picostatus"
MQTT_TOPIC_AVAIL = "homeassistant/accontroller/accontroller/availability"
MQTT_DISCOVERY_TOPIC = "homeassistant/climate/pico_ac/config"
MQTT_SUB_NEW_BROKER = "homeassistant/accontroller/setbroker"