import cv2
import time
import json
import base64
import threading
from collections import defaultdict
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator, colors


class VideoProcessor:
    def __init__(self, video_path, port, mqtt_client, ws_server):
        self.video_path = video_path
        self.port = port
        self.mqtt_client = mqtt_client
        self.ws_server = ws_server
        self.model = YOLO("models/yolo12n.pt")  # Load YOLO Model
        self.target_classes = {1, 2, 3, 5, 7}  # Vehicle classes
        self.class_track_ids = defaultdict(set)  # Unique vehicle ID tracking
        self.stop_event = threading.Event()  # Flag to stop processing
        self.clients_connected = True  # Assume WebSocket clients are active

    def send_frame_to_clients(self, frame, vehicle_counts):
        """Encodes and sends the frame + vehicle counts via WebSocket."""
        message = {"frame": frame, "vehicle_counts": vehicle_counts}
        self.ws_server.send_frame(json.dumps(message))

    def process_stream(self):
        """Reads video, detects vehicles, streams frames via WebSocket & sends density to MQTT."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"❌ Error: Unable to open video file {self.video_path}")
            return

        w, h, fps = (
            int(cap.get(x))
            for x in (
                cv2.CAP_PROP_FRAME_WIDTH,
                cv2.CAP_PROP_FRAME_HEIGHT,
                cv2.CAP_PROP_FPS,
            )
        )
        print(f"🎥 Processing video {self.video_path} at {fps} FPS")

        frame_skip = max(1, int(fps / 15))  # Reduce processing load

        try:
            frame_count = 0
            while not self.stop_event.is_set():
                if not self.clients_connected:
                    time.sleep(0.1)
                    continue

                ret, im0 = cap.read()
                if not ret:
                    print(f"✅ Video processing completed for {self.video_path}.")
                    break

                if im0.shape[1] != w or im0.shape[0] != h:
                    im0 = cv2.resize(im0, (w, h))

                if frame_count % frame_skip == 0:
                    annotator = Annotator(im0, line_width=2)
                    results = self.model.track(im0, persist=True)

                    if results[0].boxes.id is not None and results[0].boxes.cls is not None:
                        bboxes = results[0].boxes.xyxy
                        track_ids = results[0].boxes.id.int().cpu().tolist()
                        class_indices = results[0].boxes.cls.int().cpu().tolist()

                        for bbox, track_id, class_idx in zip(bboxes, track_ids, class_indices):
                            if class_idx in self.target_classes:
                                class_name = self.model.names[class_idx]
                                label = f"{class_name} {track_id}"
                                self.class_track_ids[class_name].add(track_id)
                                annotator.box_label(bbox, label, color=colors(track_id, True))

                    _, buffer = cv2.imencode(".jpg", im0, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    encoded_frame = base64.b64encode(buffer).decode("utf-8")

                    # Count unique vehicles
                    vehicle_counts = {cls: len(ids) for cls, ids in self.class_track_ids.items()}

                    # Send frame to WebSocket clients
                    self.send_frame_to_clients(encoded_frame, vehicle_counts)

                    # Publish data to MQTT
                    self.mqtt_client.publish(f"traffic/density/{self.port}", json.dumps(vehicle_counts))

                frame_count += 1

        except Exception as e:
            print(f"⚠️ Error processing {self.video_path}: {e}")

        finally:
            cap.release()
