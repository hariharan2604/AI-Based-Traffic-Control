import json
import threading
import paho.mqtt.client as mqtt
import logging
from config.settings import MQTT_BROKER, MQTT_PORT

# Enable logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [MQTT] %(message)s")

manual_override = {}
vehicle_density_data = {}

# Thread locks
manual_override_lock = threading.Lock()
vehicle_data_lock = threading.Lock()

def on_message(client, userdata, message):
    """Handles incoming MQTT messages for manual overrides and traffic density."""
    global manual_override, vehicle_density_data
    topic = message.topic
    payload = message.payload.decode()

    logging.info(f"📩 Received MQTT message: Topic: {topic}, Payload: {payload}")

    try:
        data = json.loads(payload)

        if topic.startswith("signal/manual/"):
            intersection = int(topic.split("/")[-1])
            with manual_override_lock:
                if data["duration"] is None:
                    manual_override.pop(intersection, None)
                    logging.info(f"🛑 Removed manual override for intersection {intersection}")
                else:
                    manual_override[intersection] = data["duration"]
                    logging.info(f"🟢 Manual override set: {intersection} → {data['duration']}s")

        elif topic.startswith("traffic/density/"):
            intersection = int(topic.split("/")[-1])
            with vehicle_data_lock:
                vehicle_density_data[intersection] = data
            logging.info(f"🚗 Traffic density updated for {intersection}: {data}")

    except json.JSONDecodeError:
        logging.error(f"⚠️ Invalid JSON in MQTT message: {payload}")

def on_connect(client, userdata, flags, rc):
    """Logs MQTT connection status."""
    if rc == 0:
        logging.info("✅ Connected to MQTT broker.")
    else:
        logging.error(f"❌ MQTT connection failed with code {rc}")

def mqtt_setup():
    """Initializes and configures the MQTT client with logging."""
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.subscribe("signal/manual/#")  # Listen for manual overrides
        client.subscribe("traffic/density/#")  # Listen for vehicle density updates
        client.loop_start()
        logging.info("📡 MQTT listening for messages...")
    except Exception as e:
        logging.error(f"🚨 MQTT connection error: {e}")

    return client
