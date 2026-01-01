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
        self._on_ready_callback = None
        self._subscriptions = []
        
        # Debug callbacks
        def on_subscribe(client, userdata, mid, granted_qos):
            print(f"[MQTT] Subscription confirmed (mid={mid}, qos={granted_qos})")
        
        def on_connect(client, userdata, flags, rc):
            print(f"[MQTT] Connected to broker (rc={rc})")
            if rc == 0:
                # Subscribe to queued topics now that we're connected
                for topic in self._subscriptions:
                    print(f"[MQTT] Subscribing to: {topic}")
                    client.subscribe(topic)
                # Call ready callback if set
                if self._on_ready_callback:
                    self._on_ready_callback()
            else:
                print(f"[MQTT] Connection failed with code {rc}")
        
        self.client.on_subscribe = on_subscribe
        self.client.on_connect = on_connect

    def on_message(self, callback):
        """Set the message callback. Must be called BEFORE connect()."""
        self.client.on_message = callback

    def on_ready(self, callback):
        """Set callback to be called when connection is ready and subscribed."""
        self._on_ready_callback = callback

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
        """Queue subscription - will be executed when connected."""
        self._subscriptions.append(topic)

    def publish(self, topic, message):
        self.client.publish(topic, message)