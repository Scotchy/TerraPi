
import os
import paho.mqtt.client as mqtt

client = mqtt.Client()

# Connect to the broker
client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASSWORD"])
client.connect("plantescarnivores.net", 1883)

# Get user input and publish to given topic
while True:
    topic = input("Topic: ")
    message = input("Message: ")
    client.publish(topic, message)

