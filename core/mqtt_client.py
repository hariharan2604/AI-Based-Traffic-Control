import json
import threading
import paho.mqtt.client as mqtt
from config.settings import MQTT_BROKER, MQTT_PORT

manual_override = {}
vehicle_density_data = {}

# Thread locks
manual_override_lock = threading.Lock()
vehicle_data_lock = threading.Lock()

def on_message(client, userdata, message):
    """Handles incoming MQTT messages for manual overrides and traffic density."""
    global manual_override, vehicle_density_data
    topic = message.topic
    payload = json.loads(message.payload.decode())

    if topic.startswith("signal/manual/"):
        intersection = int(topic.split("/")[-1])
        with manual_override_lock:
            if payload["duration"] is None:
                manual_override.pop(intersection, None)
                print(f"Manual override removed for {intersection}")
            else:
                manual_override[intersection] = payload["duration"]
                print(f"Manual override set for {intersection}: {payload['duration']}s")

    elif topic.startswith("traffic/density/"):
        intersection = int(topic.split("/")[-1])
        with vehicle_data_lock:
            vehicle_density_data[intersection] = payload  # Store real-time density
        print(f"Received density for {intersection}: {payload}")  # Debugging

def mqtt_setup():
    """Initializes and configures the MQTT client."""
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.on_message = on_message
    client.subscribe("signal/manual/#")  # Listen for manual overrides
    client.subscribe("traffic/density/#")  # Listen for vehicle density updates
    client.loop_start()
    return client
