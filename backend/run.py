import terrapi as tp
from terrapi.config_loader import load_config
import click
import time
import os
import board
import adafruit_dht
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

follow_planning = True 
current_mode = None
devices_pins = {} 


@click.command()
@click.option('--conf', help='Path to config file', default='conf/config.yaml')
def run(conf):
    run_robust(conf)


def run_robust(conf):

    client = None 

    while True:
        try:
            global follow_planning
            global current_mode
            global devices_pins

            # Load config file
            config = load_config(conf)

            # Create the terrarium
            terrarium = tp.terrarium.Terrarium(config)

            # Create MQTT client with SSL options
            use_ssl = getattr(config.mqtt, 'use_ssl', False)
            ca_certs = getattr(config.mqtt, 'ca_certs', None)
            host, port = config.mqtt.host, config.mqtt.port
            user, password = config.mqtt.user, config.mqtt.password
            if os.environ.get("TERRAPI_MANAGED_TLS") == "1":
                host, port = os.environ["MQTT_HOST"], int(os.environ["MQTT_PORT"])
                user, password = os.environ["MQTT_USER"], os.environ["MQTT_PASSWORD"]
                use_ssl = True
            client = tp.client.MosquittoClient(host, port, use_ssl, ca_certs)

            # Create TerraHandler (sets up message handler)
            terra_handler = tp.terra_handler.TerraHandler(terrarium, client, config, conf)

            # Now connect (after message handler is set)
            client.connect(user, password)

            # run 
            try:
                terra_handler.run()
            finally:
                terra_handler.close()
        
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
