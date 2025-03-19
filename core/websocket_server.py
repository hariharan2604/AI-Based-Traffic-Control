import threading
from websocket_server import WebsocketServer

class WebSocketServer:

    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.server = WebsocketServer(host=self.host, port=self.port)

        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)

        self.client_count = 0
        self.client_event = threading.Event()  # Event to notify client connection

    def new_client(self, client, server):
        """Handles new client connections."""
        self.client_count += 1
        self.client_event.set()  # Signal processing to start
        print(f"✅ [WebSocket {self.port}] New client connected: {client} (Total: {self.client_count})")

    def client_left(self, client, server):
        """Handles client disconnections."""
        self.client_count -= 1
        if self.client_count == 0:
            self.client_event.clear()  # Signal processing to stop
        print(f"❌ [WebSocket {self.port}] Client disconnected: {client} (Remaining: {self.client_count})")

    def send_frame(self, message):
        """Sends encoded frame + vehicle counts via WebSocket."""
        self.server.send_message_to_all(message)

    def start_in_thread(self):
        """Starts WebSocket server in a new thread."""
        thread = threading.Thread(target=self.server.run_forever, daemon=True)
        thread.start()
