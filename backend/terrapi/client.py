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
        
        # Debug callbacks
        def on_subscribe(client, userdata, mid, granted_qos):
            print(f"[MQTT] Subscription confirmed (mid={mid}, qos={granted_qos})")
        
        def on_connect(client, userdata, flags, rc):
            print(f"[MQTT] Connected to broker (rc={rc})")
        
        self.client.on_subscribe = on_subscribe
        self.client.on_connect = on_connect

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