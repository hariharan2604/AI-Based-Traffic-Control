import json
import threading
import paho.mqtt.client as mqtt
import logging
import sys

from config.settings import MQTT_BROKER, MQTT_PORT

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s [%(module)s] %(message)s"
)

manual_override = {}
vehicle_density_data = {}
emergency_events = set()

manual_override_lock = threading.Lock()
vehicle_data_lock = threading.Lock()
emergency_lock = threading.Lock()


def on_message(client, userdata, message):
    global manual_override, vehicle_density_data, emergency_events

    topic = message.topic
    payload = message.payload.decode()

    try:
        data = json.loads(payload)

        if topic.startswith("signal/manual/"):
            intersection = int(topic.split("/")[-1])
            with manual_override_lock:
                if data["duration"] is None:
                    manual_override.pop(intersection, None)
                else:
                    manual_override[intersection] = data["duration"]

        elif topic.startswith("traffic/density/"):
            intersection = int(topic.split("/")[-1])
            with vehicle_data_lock:
                vehicle_density_data[intersection] = data

        elif topic.startswith("traffic/emergency/"):
            intersection = int(topic.split("/")[-1])
            with emergency_lock:
                if data.get("emergency"):
                    emergency_events.add(intersection)
                    logging.info(
                        f"🚨 Emergency vehicle detected at intersection {intersection}"
                    )
                else:
                    emergency_events.discard(intersection)
                    logging.info(f"🚨 Emergency cleared at intersection {intersection}")

    except json.JSONDecodeError:
        logging.error(f"⚠️ Invalid JSON in MQTT message: {payload}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("✅ Connected to MQTT broker.")
    else:
        logging.error(f"❌ MQTT connection failed with code {rc}")


def mqtt_setup():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe("signal/manual/#")
    client.subscribe("traffic/density/#")
    client.subscribe("traffic/emergency/#")
    client.loop_start()

    logging.info("📡 MQTT listening for messages...")
    return client
