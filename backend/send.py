
import os
import paho.mqtt.client as mqtt

client = mqtt.Client()

# Connect to the broker
client.tls_set()
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASSWORD"])
client.connect(os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", "1883")))

# Get user input and publish to given topic
while True:
    topic = input("Topic: ")
    message = input("Message: ")
    client.publish(topic, message)

