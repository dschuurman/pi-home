# Home-sense program for use with Zigbee devices and a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# Constants
TEMPERATURE_HYSTERESIS = 1.0
HUMIDITY_HYSTERESIS = 2.0

class State:
    ''' Class to store and retrieve sensor states
    '''
    def __init__(self, sensors, low_temp_threshold, high_humidity_threshold):
        ''' Constructor 
        ''' 
        # Temp and humidity thresholds to trigger an alert
        self.low_temp_threshold = low_temp_threshold
        self.high_hunidity_threshold = high_humidity_threshold

        # Initialize states to None
        self.temperature = None
        self.humidity = None
        self.pressure = None
        self.water_leak = False
        self.low_battery = False

    def set_temperature(self, temp):
        self.temperature = temp

    def set_humidity(self, humidity):
        self.humidity = humidity

    def set_pressure(self, pressure):
        self.pressure = pressure

    def get_temperature(self):
        return self.temperature

    def get_humidity(self):
        return self.humidity

    def get_pressure(self):
        return self.pressure

    def get_water_leak(self):
        return self.water_leak

    def is_low_temp(self):
        if self.temperature == None:
            return False
        else:
            return self.temperature < self.low_temp_threshold

    def is_freezing(self):
        if self.temperature == None:
            return False
        else:
            return self.temperature < 0.0

    def is_above_freezing(self):
        if self.temperature == None:
            return False
        else:
            return self.temperature > TEMPERATURE_HYSTERESIS 

    def is_temp_normal(self):
        if self.temperature == None:
            return False
        else:
            return self.temperature > self.low_temp_threshold + TEMPERATURE_HYSTERESIS

    def is_high_humidity(self):
        if self.humidity == None:
            return False
        else:
            return self.humidity > self.high_hunidity_threshold

    def is_humidity_normal(self):
        if self.humidity == None:
            return False
        else:
            return self.humidity < self.high_hunidity_threshold - HUMIDITY_HYSTERESIS

if __name__ == '__main__':
    state = State('', 10, 80)
    state.set_temperature(10)
    assert (state.get_temperature() == 10)
    state.set_humidity(10)
    assert (state.get_humidity() == 10)
    state.set_pressure(1000)
    assert (state.get_pressure() == 1000)
    state.set_temperature(1+TEMPERATURE_HYSTERESIS)
    assert (state.is_above_freezing() == True)
    state.set_temperature(-1)
    assert (state.is_above_freezing() == False)
    state.set_temperature(8)
    assert (state.is_temp_normal() == False)
    state.set_temperature(11+TEMPERATURE_HYSTERESIS)
    assert (state.is_temp_normal() == True)
    state.set_humidity(80)
    assert (state.is_high_humidity() == False)
    state.set_humidity(81)
    assert (state.is_high_humidity() == True)
    state.set_humidity(79-HUMIDITY_HYSTERESIS)
    assert (state.is_humidity_normal() == True)