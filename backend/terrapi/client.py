import paho.mqtt.client as mqtt


from .monitoring import ACK_TOPIC


class MosquittoClient:
    topics = ("planning/active", "mode/set", "config/get", "config/update")

    def __init__(self, settings):
        self.client = mqtt.Client()
        self.ready = False
        self.client.max_queued_messages_set(8)
        self.host = settings["host"]
        self.port = settings["port"]
        self.client.username_pw_set(settings["user"], settings["password"])
        if settings.get("use_ssl"):
            self.client.tls_set(ca_certs=settings.get("ca_certs"))

    def start(self, on_message, on_ready):
        def connected(client, userdata, flags, rc):
            self.ready = False
            if rc == 0:
                client.subscribe([(topic, 0) for topic in self.topics])
                client.subscribe(ACK_TOPIC, qos=1)

        def subscribed(client, userdata, mid, qos):
            if len(qos) == len(self.topics) and 128 not in qos:
                self.ready = True
                on_ready()

        def disconnected(client, userdata, rc):
            self.ready = False

        self.client.on_disconnect = disconnected
        self.client.on_connect = connected
        self.client.on_subscribe = subscribed
        self.client.on_message = on_message
        self.client.connect_async(self.host, self.port)
        self.client.loop_start()

    def disconnect(self):
        self.client.disconnect()
        self.client.loop_stop()

    def is_connected(self):
        return self.client.is_connected()

    def publish(self, topic, payload, qos=0):
        return self.client.publish(topic, payload, qos=qos)
