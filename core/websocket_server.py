import threading
import logging
import sys
from websocket_server import WebsocketServer


class WebSocketServer:

    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.server = WebsocketServer(host=self.host, port=self.port)
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)
        self.client_count = 0
        self.client_event = threading.Event()  #
        logging.basicConfig(level=logging.INFO,format="%(asctime)s %(name)s [%(module)s] %(message)s")

    def new_client(self, client, server):
        self.client_count += 1
        self.client_event.set()
        logging.info(
            f"✅ [WebSocket {self.port}] New client connected: {client} (Total: {self.client_count})"
        )

    def client_left(self, client, server):
        self.client_count -= 1
        if self.client_count == 0:
            self.client_event.clear()
        logging.error(
            f"❌ [WebSocket {self.port}] Client disconnected: {client} (Remaining: {self.client_count})"
        )

    def send_frame(self, message):
        self.server.send_message_to_all(message)

    def start_in_thread(self):
        thread = threading.Thread(target=self.server.run_forever, daemon=True)
        thread.start()
