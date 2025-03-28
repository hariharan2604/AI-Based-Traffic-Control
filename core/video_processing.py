import cv2
import json
import threading
import base64
import queue
import logging
import sys

from collections import defaultdict
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator, colors


class VideoProcessor:
    def __init__(self, video_path, port, mqtt_client, ws_server):
        self.video_path = video_path
        self.port = port
        self.mqtt_client = mqtt_client
        self.ws_server = ws_server
        self.model = YOLO("models/yolo12n.engine", task='detect')
        self.target_classes = {1, 2, 3, 5, 7}
        self.class_track_ids = defaultdict(set)
        self.class_track_ids_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=1)
        self.clients_connected = False
        
        logging.getLogger(__name__).addHandler(logging.StreamHandler(sys.stdout))
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(message)s",
        )
        
        self.stream_thread = threading.Thread(target=self.stream_frames, daemon=True)
        self.stream_thread.start()

    def send_frame_to_clients(self, frame, vehicle_counts):
        message = {"frame": frame, "vehicle_counts": vehicle_counts}
        self.ws_server.send_frame(json.dumps(message))

    def process_stream(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            logging.error(f"❌ Error: Unable to open video file {self.video_path}")
            return

        w, h, fps = (
            int(cap.get(x))
            for x in (
                cv2.CAP_PROP_FRAME_WIDTH,
                cv2.CAP_PROP_FRAME_HEIGHT,
                cv2.CAP_PROP_FPS,
            )
        )
        logging.info(f"🎥 Processing video {self.video_path} at {fps} FPS")

        try:
            while not self.stop_event.is_set():
                if self.ws_server.client_count == 0:
                    if not self.clients_connected:
                        logging.info(f"⏸️ Waiting for WebSocket clients on port {self.port}...")
                        self.clients_connected = True
                    self.ws_server.client_event.wait()
                else:
                    self.clients_connected = False

                ret, im0 = cap.read()
                if not ret:
                    logging.info(f"✅ Video processing completed for {self.video_path}.")
                    break

                if im0.shape[1] != w or im0.shape[0] != h:
                    im0 = cv2.resize(im0, (w, h))

                annotator = Annotator(im0, line_width=2)
                try:
                    results = self.model.track(im0, persist=True, tracker="datasets/bytetrack.yaml")
                except Exception as e:
                    logging.error(f"⚠️ YOLO inference error: {e}")
                    continue

                if results[0].boxes.id is not None and results[0].boxes.cls is not None:
                    bboxes = results[0].boxes.xyxy
                    track_ids = results[0].boxes.id.int().cpu().tolist()
                    class_indices = results[0].boxes.cls.int().cpu().tolist()

                    with self.class_track_ids_lock:
                        for bbox, track_id, class_idx in zip(bboxes, track_ids, class_indices):
                            if class_idx in self.target_classes:
                                class_name = self.model.names[class_idx]
                                label = f"{class_name} {track_id}"
                                self.class_track_ids[class_name].add(track_id)
                                annotator.box_label(bbox, label, color=colors(track_id, True))

                _, buffer = cv2.imencode(".jpg", im0, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                encoded_frame = base64.b64encode(buffer).decode("utf-8")

                with self.class_track_ids_lock:
                    vehicle_counts = {cls: len(ids) for cls, ids in self.class_track_ids.items() if ids}

                if not self.frame_queue.full():
                    self.frame_queue.put((encoded_frame, vehicle_counts))

                self.mqtt_client.publish(f"traffic/density/{self.port}", json.dumps(vehicle_counts))
        
        except Exception as e:
            logging.error(f"⚠️ Error processing {self.video_path}: {e}")
        
        finally:
            cap.release()

    def stream_frames(self):
        while not self.stop_event.is_set():
            try:
                frame, vehicle_counts = self.frame_queue.get(timeout=0.05)
                self.send_frame_to_clients(frame, vehicle_counts)
            except queue.Empty:
                pass

    def stop(self):
        self.stop_event.set()
        self.stream_thread.join()
        self.mqtt_client.disconnect()
        self.ws_server.close()