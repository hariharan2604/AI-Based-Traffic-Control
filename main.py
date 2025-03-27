import threading
import logging
import sys
from config.settings import VIDEO_SOURCES
from core.video_processing import VideoProcessor
from core.traffic_signal_control import cycle_signals
from core.mqtt_client import mqtt_setup
from core.websocket_server import WebSocketServer

logging.getLogger(__name__).addHandler(logging.StreamHandler(sys.stdout))
logging.basicConfig(
level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
)


def start_video_processing(mqtt_client, ws_servers):
    threads = []

    for (video_path, port), ws_server in zip(VIDEO_SOURCES, ws_servers):
        processor = VideoProcessor(video_path, port, mqtt_client, ws_server)
        thread = threading.Thread(target=processor.process_stream, daemon=True)
        thread.start()
        threads.append(thread)
        logging.info(
            f"📹 Started video processing for {video_path} on WebSocket {port}"
        )

    return threads


if __name__ == "__main__":
    ws_servers = [WebSocketServer(port=port) for _, port in VIDEO_SOURCES]

    for ws_server in ws_servers:
        ws_server.start_in_thread()

    mqtt_client = mqtt_setup()

    video_threads = start_video_processing(mqtt_client, ws_servers)

    signal_management_thread = threading.Thread(
        target=cycle_signals, args=(mqtt_client, ws_servers), daemon=True
    )
    signal_management_thread.start()

    for thread in video_threads:
        thread.join()
