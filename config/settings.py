# settings.py: Stores configurations for MQTT, ACO parameters, and WebSockets

MQTT_BROKER = "localhost"
MQTT_PORT = 1883

WEBSOCKET_HOST = "127.0.0.1"
WEBSOCKET_PORT = 5000

VIDEO_SOURCES = [
    ("samples/inter1.mp4", 4001),
    ("samples/inter2.mp4", 4002),
    ("samples/inter3.mp4", 4003),
    ("samples/inter4.mp4", 4004),
]

ACO_DEFAULT_DURATION = 30  # Default signal time (seconds)
ACO_MAX_DURATION = 90  # Maximum green light duration
MIN_UPDATE_THRESHOLD = 5  # Only update signals if change is 5+ seconds
BASE_YELLOW_DURATION = 5
BASE_RED_DURATION = 40
EMERGENCY_THRESHOLD = 200
EMERGENCY_GREEN_BOOST = 20
