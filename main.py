import threading
from config.settings import VIDEO_SOURCES
from core.video_processing import VideoProcessor
from core.traffic_signal_control import manage_traffic_signals
from core.mqtt_handler import mqtt_setup
from core.websocket_server import WebSocketServer

def start_video_processing(mqtt_client, ws_server):
    """Starts video processing threads for all intersections."""
    threads = []
    for video_path, port in VIDEO_SOURCES:
        processor = VideoProcessor(video_path, port, mqtt_client, ws_server)
        thread = threading.Thread(target=processor.process_stream)
        thread.start()
        threads.append(thread)

    return threads

if __name__ == "__main__":
    ws_server = WebSocketServer()
    threading.Thread(target=ws_server.start).start()

    mqtt_client = mqtt_setup()

    video_threads = start_video_processing(mqtt_client, ws_server)

    threading.Thread(target=manage_traffic_signals, args=(mqtt_client,)).start()

    for thread in video_threads:
        thread.join()
