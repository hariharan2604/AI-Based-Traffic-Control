import json
import logging
from threading import Lock

import paho.mqtt.client as mqtt

from config.settings import MQTT_BROKER, MQTT_PORT

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s [%(module)s] %(message)s"
)

vehicle_density_data = {}
vehicle_data_lock = Lock()

# manual_override = False
manual_override = {"active": False}
manual_override_lock = Lock()

emergency_events = set()

DENSITY_TOPIC_PREFIX = "traffic/density/"
MANUAL_OVERRIDE_TOPIC = "signal/manual/"
EMERGENCY_TOPIC = "traffic/emergency/"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("✅ MQTT connected successfully.")
        client.subscribe([(DENSITY_TOPIC_PREFIX + "#", 0), (MANUAL_OVERRIDE_TOPIC+"#", 0), (EMERGENCY_TOPIC+"#", 0)])
    else:
        logging.error(f"❌ MQTT connection failed with code {rc}")


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logging.warning(f"⚠️ Invalid JSON on topic {topic}: {payload}")
        return

    if topic.startswith(DENSITY_TOPIC_PREFIX):
        signal_id = topic.split("/")[-1]
        with vehicle_data_lock:
            vehicle_density_data[signal_id] = data

    elif topic.startswith(MANUAL_OVERRIDE_TOPIC):
        global manual_override
        with manual_override_lock:
            manual_override["active"] = bool(data.get("set", False))
        logging.info(f"🛠 Manual override set to {manual_override}")

    elif topic.startswith(EMERGENCY_TOPIC):
        try:
            signal_id = int(topic.split("/")[-1])
        except ValueError:
            logging.warning(f"⚠️ Invalid emergency signal ID in topic: {topic}")
            return

        if data.get("status", "").lower() == "start":
            emergency_events.add(signal_id)
            logging.info(f"🚨 Emergency STARTED at signal {signal_id}")
        elif data.get("status", "").lower() == "clear":
            emergency_events.discard(signal_id)
            logging.info(f"✅ Emergency CLEARED at signal {signal_id}")
        else:
            logging.warning(f"⚠️ Unknown emergency status on topic {topic}: {payload}")


def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        logging.error(f"❌ Failed to connect to MQTT broker: {e}")
        raise e

    logging.info("🚀 MQTT client started and looping...")
    client.loop_start()
    return client
