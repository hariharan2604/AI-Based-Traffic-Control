import cv2
import json
import time
import base64
from ultralytics import YOLO
from collections import defaultdict
import paho.mqtt.client as mqtt
from config.settings import VIDEO_SOURCES
from core.websocket_server import WebSocketServer

class VideoProcessor:
    def __init__(self, video_path, port, mqtt_client, ws_server):
        self.video_path = video_path
        self.port = port
        self.mqtt_client = mqtt_client
        self.ws_server = ws_server
        self.model = YOLO("models/yolo12x.pt")

    def get_vehicle_density(self, results):
        """Extracts vehicle counts from YOLO tracking results."""
        density = defaultdict(int)
        if results[0].boxes.id is not None:
            for class_idx in results[0].boxes.cls.int().cpu().tolist():
                if class_idx in {1, 2, 3, 5, 7}:  # Vehicle classes
                    class_name = self.model.names[class_idx]
                    density[class_name] += 1
        return density

    def process_stream(self):
        """Reads video, detects vehicles, publishes density via MQTT, and streams via WebSocket."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"Error: Unable to open video {self.video_path}")
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            results = self.model.track(frame, persist=True)
            vehicle_counts = self.get_vehicle_density(results)

            # Encode frame to JPEG
            _, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            encoded_frame = base64.b64encode(buffer).decode("utf-8")

            # Publish vehicle data to MQTT
            self.mqtt_client.publish(f"traffic/density/{self.port}", json.dumps(vehicle_counts))

            # Stream processed frame via WebSocket
            self.ws_server.send_frame(encoded_frame, vehicle_counts)

            time.sleep(1)  # Adjust for frame rate
