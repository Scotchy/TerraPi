import paho.mqtt.client as mqtt

class Client():

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.client = None


class MosquittoClient(Client):

    def __init__(self, host, port):
        super().__init__(host, port)
        self.client = mqtt.Client()

    def on_message(self, callback):
        """Set the message callback. Must be called BEFORE connect()."""
        self.client.on_message = callback

    def connect(self, username, password):
        self.client.username_pw_set(username, password)
        self.client.connect(self.host, self.port)
        self.client.loop_start()  # Start background thread to process messages

    def send_message(self, topic, message):
        self.client.publish(topic, message)
        
    def disconnect(self):
        self.client.loop_stop()  # Stop background thread
        self.client.disconnect()

    def subscribe(self, topic):
        self.client.subscribe(topic)

    def publish(self, topic, message):
        self.client.publish(topic, message)