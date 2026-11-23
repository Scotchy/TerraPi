import paho.mqtt.client as mqtt
import ssl
from threading import Event

class Client():

    def __init__(self, host, port, use_ssl=False, ca_certs=None):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.ca_certs = ca_certs
        self.client = None


class MosquittoClient(Client):

    def __init__(self, host, port, use_ssl=False, ca_certs=None):
        super().__init__(host, port, use_ssl, ca_certs)
        self.client = mqtt.Client()
        self.client.max_queued_messages_set(8)
        self._connected = Event()
        self._on_ready_callback = None
        self._subscriptions = []
        
        # Configure TLS if enabled
        if use_ssl:
            if ca_certs:
                self.client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLS)
            else:
                # Use system CA certificates
                self.client.tls_set(tls_version=ssl.PROTOCOL_TLS)
        
        # Debug callbacks
        def on_subscribe(client, userdata, mid, granted_qos):
            print(f"[MQTT] Subscription confirmed (mid={mid}, qos={granted_qos})")
        
        def on_connect(client, userdata, flags, rc):
            print(f"[MQTT] Connected to broker (rc={rc})")
            if rc == 0:
                # Subscribe to queued topics now that we're connected
                for topic, qos in self._subscriptions:
                    print(f"[MQTT] Subscribing to: {topic}")
                    client.subscribe(topic, qos=qos)
                self._connected.set()
                # Call ready callback if set
                if self._on_ready_callback:
                    self._on_ready_callback()
            else:
                print(f"[MQTT] Connection failed with code {rc}")
        
        self.client.on_subscribe = on_subscribe
        self.client.on_connect = on_connect
        self.client.on_disconnect = lambda client, userdata, rc: self._connected.clear()

    def is_connected(self):
        return self._connected.is_set()

    def on_message(self, callback):
        """Set the message callback. Must be called BEFORE connect()."""
        self.client.on_message = callback

    def on_ready(self, callback):
        """Set callback to be called when connection is ready and subscribed."""
        self._on_ready_callback = callback

    def connect(self, username, password):
        self.client.username_pw_set(username, password)
        # Start sampling and controlling the terrarium even if the broker is down at boot.
        self.client.connect_async(self.host, self.port, keepalive=20)
        self.client.loop_start()  # Start background thread to process messages

    def send_message(self, topic, message):
        self.client.publish(topic, message)
        
    def disconnect(self):
        self.client.disconnect()
        self.client.loop_stop()

    def subscribe(self, topic, qos=0):
        """Queue subscription - will be executed when connected."""
        self._subscriptions.append((topic, qos))

    def publish(self, topic, message, qos=0):
        return self.client.publish(topic, message, qos=qos)
