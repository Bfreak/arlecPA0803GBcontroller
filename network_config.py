# add your wifi and MQTT credentials here
WIFI_SSID = "yourWifiSSIDhere"
WIFI_PASSWORD = "YourWifiPasswordHere"

#Start your homeassistant and make sure you have the MQTT add-on, and change the following to your needs 
MQTT_username = "username"
MQTT_password = "password"
MQTT_BROKER = "homeassistant.local"  # or use the IP address of your MQTT broker
MQTT_PORT = 1883
MQTT_CLIENT_ID = "ACcontroller"
MQTT_SUB_MODE = "homeassistant/accontroller/requested_mode" # mode requested by Home Assistant
MQTT_TOPIC_MODE = "homeassistant/accontroller/reported_mode" # mode reported to Home Assistant
MQTT_REAL_MODE = "homeassistant/accontroller/real_mode" # mode actually set on the AC
MQTT_SUB_TEMP = "homeassistant/accontroller/requested_temp" # temperature requested by Home Assistant
MQTT_TOPIC_TEMP = "homeassistant/accontroller/reported_temp" # temperature reported to Home Assistant
MQTT_REAL_TEMP = "homeassistant/accontroller/real_temp" # temperature actually set on the AC
MQTT_TOPIC_STATUS = "homeassistant/accontroller/picostatus"
MQTT_TOPIC_AVAIL = "homeassistant/accontroller/accontroller/availability"
MQTT_DISCOVERY_TOPIC = "homeassistant/climate/pico_ac/config"
MQTT_SUB_NEW_BROKER = "homeassistant/accontroller/setbroker"
