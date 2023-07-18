import terrapi as tp
from xpipe.config import load_config
import click
import time
import board
import adafruit_dht
import RPi.GPIO as GPIO

follow_planning = True 
current_mode = None
devices_pins = {} 


@click.command()
@click.option('--conf', help='Path to config file', required=True)
def run(conf):
    run_robust(conf)


def run_robust(conf):

    client = None 

    while True:
        try:
            global follow_planning
            global current_mode
            global devices_pins

            follow_planning = True 
            current_mode = None
            devices_pins = {} 

            GPIO.setmode(GPIO.BCM)

            # Load config file
            config = load_config(conf)

            # Connect to mosquitto broker
            client = tp.client.MosquittoClient(config.mqtt.host(), config.mqtt.port())
            client.connect(config.mqtt.user(), config.mqtt.password())

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
            # Print whole stack trace
            import traceback
            traceback.print_exc()
            
            print("Retrying in 10s")

            GPIO.cleanup()

            if client is not None:
                client.disconnect()
            time.sleep(10)

run()