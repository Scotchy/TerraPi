import board
import adafruit_dht

class Sensor():

    def __init__(self, pin):
        self._pin = pin

    def get_data(self):
        pass


class DHT22(Sensor):

    def __init__(self, pin):
        super().__init__(pin)

    def get_data(self):
        dht_pin = self._pin
        dht_pin = getattr(board, f"D{dht_pin}")
        dht_device = adafruit_dht.DHT22(dht_pin)

        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            return {
                "temperature": temperature,
                "humidity": humidity
            }
        except RuntimeError as error:
            print(error.args[0])
            return None