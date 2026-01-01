
# MQTT client 
import paho.mqtt.client as mqtt

client = mqtt.Client()

# Connect to the broker
client.username_pw_set("jules", "dfgcegfv4859")
client.connect("plantescarnivores.net", 1883)

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
