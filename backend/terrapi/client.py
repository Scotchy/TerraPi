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

    def connect(self, username, password):
        self.client.username_pw_set(username, password)
        self.client.connect(self.host, self.port)

    def send_message(self, topic, message):
        self.client.publish(topic, message)

    def on_message(self, callback):
        self.client.on_message = callback
        
    def disconnect(self):
        self.client.disconnect()

    def subscribe(self, topic):
        self.client.subscribe(topic)

    def publish(self, topic, message):
        self.client.publish(topic, message)