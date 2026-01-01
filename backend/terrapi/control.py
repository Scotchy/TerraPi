import RPi.GPIO as GPIO

class Control():

    def __init__(self, pin):
        self._pin = pin
        self._state = False

    def switch_on(self):
        pass

    def switch_off(self):
        pass


class Relay(Control):

    def __init__(self, pin):
        super().__init__(pin)

        GPIO.setup(self._pin, GPIO.OUT)
        self.switch_off()

    def switch_on(self):
        GPIO.output(self._pin, GPIO.LOW)
        self._state = True

    def switch_off(self):
        GPIO.output(self._pin, GPIO.HIGH)
        self._state = False

    def switch(self, state):
        if state:
            self.switch_on()
        else:
            self.switch_off()