import terrapi as tp
import xpipe
import click
import time
import board
import adafruit_dht
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

follow_planning = True 
current_mode = None
devices_pins = {} 


def handle_message(client, userdata, message):
    # Topics possible: 
    #  - planning/active 
    #  - mode/set (works only if planning is not active)

    global follow_planning
    global current_mode

    # Get the topic and the message
    topic = message.topic
    message = message.payload.decode("utf-8")

    if topic == "planning/active":
        follow_planning = message == "1"

    elif topic == "mode/set":
        if not follow_planning:
            current_mode = message
    else:
        print(f"Unknown topic {topic}")


@click.command()
@click.option('--conf', help='Path to config file', required=True)
def run(conf):
    run_robust(conf)


def run_robust(conf):

    while True:
        try:
            global follow_planning
            global current_mode
            global devices_pins

            # Load config file
            config = xpipe.load_conf(conf)

            # Connect to mosquitto broker
            client = tp.client.MosquittoClient(config.mqtt.host(), config.mqtt.port())
            client.connect(config.mqtt.username(), config.mqtt.password())

            # Create the terrarium
            terrarium = tp.terrarium.Terrarium(config)

            # Create TerraHandler
            terra_handler = tp.terra_handler.TerraHandler(terrarium, client, config)

            # run 
            terra_handler.run()
        
        except KeyboardInterrupt:
            print("Exiting")
            GPIO.cleanup()
            client.disconnect()
            exit(0)

        except Exception as e:
            print("Retrying in 10s")
            GPIO.cleanup()
            client.disconnect()
            time.sleep(10)

run()