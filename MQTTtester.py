from umqttsimple import MQTTClient
import time

client = MQTTClient("testclient123", "192.168.1.200", port=1883)
try:
    client.connect(clean_session=False)
    print("Connected!")
    client.publish("test/topic", "hello")
    client.disconnect()
except Exception as e:
    print("Failed to connect:", e)