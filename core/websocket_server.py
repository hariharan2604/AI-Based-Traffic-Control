import threading
from websocket_server import WebsocketServer

class WebSocketServer:
    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.server = WebsocketServer(host=self.host, port=self.port)
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)

    def new_client(self, client, server):
        print(f"✅ [WebSocket {self.port}] New client connected: {client}")

    def client_left(self, client, server):
        print(f"❌ [WebSocket {self.port}] Client disconnected: {client}")

    def send_frame(self, message):
        """Sends encoded frame + vehicle counts via WebSocket."""
        self.server.send_message_to_all(message)

    def start_in_thread(self):
        """Starts WebSocket server in a new thread."""
        thread = threading.Thread(target=self.server.run_forever, daemon=True)
        thread.start()
