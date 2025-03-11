import json
from websocket_server import WebsocketServer

class WebSocketServer:
    def __init__(self, host="127.0.0.1", port=5000):
        self.server = WebsocketServer(host=host, port=port)
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)

    def new_client(self, client, server):
        print(f"New WebSocket client connected: {client}")

    def client_left(self, client, server):
        print(f"WebSocket client disconnected: {client}")

    def send_frame(self, frame, vehicle_counts):
        """Sends encoded frame and vehicle counts via WebSocket."""
        message = {
            "frame": frame,
            "vehicle_counts": vehicle_counts,
        }
        self.server.send_message_to_all(json.dumps(message))
    
    def start(self):
        """Runs WebSocket server."""
        self.server.run_forever()
