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
        dht_pin = self._pin
        dht_pin = getattr(board, f"D{dht_pin}")
        self.dht_device = adafruit_dht.DHT22(dht_pin)

    def get_data(self):

        try:
            temperature = self.dht_device.temperature
            humidity = self.dht_device.humidity
            return {
                "temperature": temperature,
                "humidity": humidity
            }
        except RuntimeError as error:
            print(error.args[0])
            return None