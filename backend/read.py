
# MQTT client 
import os
import paho.mqtt.client as mqtt

client = mqtt.Client()

# Connect to the broker
client.tls_set()
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASSWORD"])
client.connect(os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", "1883")))

# Subscribe to topics
client.subscribe("planning/active")
client.subscribe("mode/set")

# Subscribe to sensors
client.subscribe("sensors/dht22/temperature")
client.subscribe("sensors/dh22/humidity")

# Print the message when a message is received
def on_message(client, userdata, message):
    print(message.topic, message.payload.decode("utf-8"))

client.on_message = on_message

# Start the loop
client.loop_forever()
