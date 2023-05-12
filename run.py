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

    global follow_planning
    global current_mode
    global devices_pins

    # Load config file
    config = xpipe.load_conf(conf)

    # Connect to mosquitto broker
    client = tp.client.MosquittoClient(config.mqtt.host(), config.mqtt.port())
    client.connect(config.mqtt.username(), config.mqtt.password())

    dht_topic = config.sensors.dht22.topic()
    dht_pin = config.sensors.dht22.pin()
    dht_pin = getattr(board, f"D{dht_pin}")
    dht_device = adafruit_dht.DHT22(dht_pin)

    client.on_message(handle_message)

    # Define devices
    for device_name, device_params in config.control.values():
        pin = device_params.pin()
        pin = getattr(board, f"D{pin}")
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH) # Switch off by default
        devices_pins[device_name] = pin


    follow_planning = config.planning.active()
    current_mode = None

    while True:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            client.send_message(dht_topic, f"{temperature},{humidity}")
        except RuntimeError as error:
            print(error.args[0])

        time.sleep(config.log_interval())

        # Get current time to set mode accordingly
        current_time = time.localtime()

        if follow_planning:
            current_period = None
            current_mode = None
            # Iterate on all periods of the planning to set the mode
            for period_name, period_params in config.planning.periods.values():
                start_time = time.strptime(period_params.start_time(), "%H:%M")
                end_time = time.strptime(period_params.end_time(), "%H:%M")

                # If the current time is between the start and end time of the period
                if start_time <= current_time <= end_time:
                    # Set the mode
                    current_period = period_name
                    current_mode = period_params.mode

        # Get the parameters of the current mode
        mode_params = config.modes[current_mode]

        # Switch on/off all the devices according to the current mode
        for device_name, device_params in conf.control.values():
            switch = mode_params.get(device_name)
            if switch is not None:
                pin = devices_pins[device_name]
                GPIO.output(pin, GPIO.LOW if switch else GPIO.HIGH)
