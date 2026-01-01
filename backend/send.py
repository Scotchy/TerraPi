
import paho.mqtt.client as mqtt

client = mqtt.Client()

# Connect to the broker
client.username_pw_set("jules", "dfgcegfv4859")
client.connect("plantescarnivores.net", 1883)

# Get user input and publish to given topic
while True:
    topic = input("Topic: ")
    message = input("Message: ")
    client.publish(topic, message)

