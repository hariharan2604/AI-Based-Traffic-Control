import threading
import logging
import sys
import signal
from config.settings import VIDEO_SOURCES
from core.video_processing import VideoProcessor
from core.traffic_signal_control import cycle_signals
from core.mqtt_client import mqtt_setup
from core.websocket_server import WebSocketServer

logging.getLogger(__name__).addHandler(logging.StreamHandler(sys.stdout))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

stop_event = threading.Event()

def start_video_processing(mqtt_client, ws_servers):
    threads = []
    processors = []

    for (video_path, port), ws_server in zip(VIDEO_SOURCES, ws_servers):
        processor = VideoProcessor(video_path, port, mqtt_client, ws_server)
        processors.append(processor)
        thread = threading.Thread(target=processor.process_stream)
        thread.start()
        threads.append(thread)
        logging.info(f"📹 Started video processing for {video_path} on WebSocket {port}")

    return threads, processors

def stop_all():
    logging.info("🛑 Stopping video processing and cleaning up...")
    stop_event.set()

    for processor in video_processors:
        processor.stop()

    for ws_server in ws_servers:
        ws_server.close()

    mqtt_client.disconnect()
    logging.info("✅ Cleanup complete. Exiting.")
    sys.exit(0)

if __name__ == "__main__":
    ws_servers = [WebSocketServer(port=port) for _, port in VIDEO_SOURCES]

    for ws_server in ws_servers:
        ws_server.start_in_thread()

    mqtt_client = mqtt_setup()

    video_threads, video_processors = start_video_processing(mqtt_client, ws_servers)

    signal_management_thread = threading.Thread(
        target=cycle_signals, args=(mqtt_client, ws_servers)
    )
    signal_management_thread.start()

    # Catch SIGINT (Ctrl+C) and SIGTERM (Process Termination)
    signal.signal(signal.SIGINT, lambda sig, frame: stop_all())
    signal.signal(signal.SIGTERM, lambda sig, frame: stop_all())

    try:
        while not stop_event.is_set():
            stop_event.wait(1)
    except KeyboardInterrupt:
        stop_all()
