import json
import paho.mqtt.client as mqtt
from config.settings import MQTT_BROKER, MQTT_PORT

manual_override = {}  # Stores manual signal overrides

def on_message(client, userdata, message):
    """Handles manual override messages."""
    global manual_override
    topic = message.topic
    payload = json.loads(message.payload.decode())

    if topic.startswith("signal/manual/"):
        intersection = topic.split("/")[-1]
        manual_override[intersection] = payload["duration"]
        print(f"Manual override set for {intersection}: {payload['duration']}s")

def mqtt_setup():
    """Initializes and configures MQTT client."""
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.on_message = on_message
    client.subscribe("signal/manual/#")  # Listen for manual override
    client.loop_start()
    return client
