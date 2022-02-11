# Home-sense program for use with Zigbee devices and a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import logging
import sqlite3
from datetime import datetime
import paho.mqtt.client as mqtt
import json

# Constants
TABLE = 'SensorData'
# Alarm codes
LOW_TEMPERATURE_ALARM = 1
FREEZING_ALARM = 2
HUMIDITY_ALARM = 3

class Events:
    ''' Event class used to handle timer and MQTT messages
    '''
    def __init__(self, state, database, mail):
        ''' Constructor 
        '''
        self.state = state
        self.mail = mail

        # Initialize a list to store alarms that occur
        self.alarms = []

        # Connect to the sqlite database and create table if not found
        self.db = sqlite3.connect(database)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {TABLE} (datetime TEXT NOT NULL, temperature double, humidity double, pressure double)')
        self.cursor = self.db.cursor()

    def timer_handler(self, signum, frame):
        ''' Timer signal handler- fires every second and manages sensor readings
        '''
        # first capture sensor readings
        temperature = self.state.get_temperature()
        humidity = self.state.get_humidity()
        pressure = self.state.get_pressure()

        # If there is no useful data, return rather than storing NULL data
        if temperature==None and humidity==None and pressure==None:
            logging.debug(f'{datetime.now()}: no valid data to store in table...')
            return

        # Insert temperature/humidity into database periodically
        logging.debug(f'{datetime.now()}: inserting data into to table: {temperature},{humidity},{pressure}')
        self.ticks = 0
        # Insert temp and humidity data into table
        sqlcmd = f"INSERT INTO {TABLE} VALUES (datetime('now','localtime'),{temperature},{humidity},{pressure})"
        sqlcmd = sqlcmd.replace('None','NULL')
        self.cursor.execute(sqlcmd)
        logging.debug("{} record inserted.".format(self.cursor.rowcount))

        # Keep just the last year of readings
        sqlcmd = f"DELETE FROM {TABLE} WHERE datetime < datetime('now','localtime','-365 days')"
        self.cursor.execute(sqlcmd)
        logging.debug("{} records deleted.".format(self.cursor.rowcount))
        self.db.commit()

    def mqtt_message_handler(self, client, data, msg):
        ''' MQTT message handler
            Send e-mail alert when water leak or low battery detected
        '''
        message = str(msg.payload.decode("utf-8"))
        sensor = msg.topic.split('/')[1]   # Extract sensor "friendly name" from MQTT topic
        logging.info(f'{datetime.now()} MQTT Message received: {message}')
        status = json.loads(message) # Parse JSON message from sensor

        # analyze MQTT message for updates on various measurements
        if "water_leak" in message:
            if status['water_leak'] and sensor not in self.alarms:
                self.mail.send(f'Water leak alarm detected for {sensor}!',message)
                logging.info(f'Water leak alarm detected for {sensor}!')
                self.alarms.append(sensor)
                self.state.water_leak = True
            elif not status['water_leak'] and sensor in self.alarms:
                self.mail.send(f'Water leak alarm stopped for {sensor}',message)
                logging.info(f'Water leak alarm stopped for {sensor}!')
                self.alarms.remove(sensor)
                self.state.water_leak = False

        if 'battery_low' in message and status['battery_low']:
            self.mail.send(f'Low battery detected for {sensor}!', message)
            logging.info(f'Low battery detected for {sensor}!')

        if 'temperature' in message:
            logging.info(f'Temperature = {status["temperature"]} degrees C')
            self.state.temperature = float(status['temperature'])
            # Next, check temperature value; send an alert if it falls below a preset threshold
            if self.state.is_low_temp() and LOW_TEMPERATURE_ALARM not in self.alarms:
                message = f'The house temperature has fallen to: {status["temperature"]} degrees C!'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature warning!', message)
                self.alarms.append(LOW_TEMPERATURE_ALARM)
            # otherwise check if temperature returns back above threshold
            elif self.state.is_temp_normal() and LOW_TEMPERATURE_ALARM in self.alarms:
                message = f'The house temperature is now risen to {status["temperature"]} degrees C.'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature update', message)
                self.alarms.remove(LOW_TEMPERATURE_ALARM)
            # check explicitly for freezing temperatures
            elif self.state.is_freezing() and FREEZING_ALARM not in self.alarms:
                message = f'The house temperature is freezing! Temperature={status["temperature"]} degrees C!'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature FREEZING!', message)
                self.alarms.append(FREEZING_ALARM)
            # otherwise check if things are no longer freezing
            elif self.state.is_above_freezing() and FREEZING_ALARM in self.alarms:
                message = f'The house temperature is now risen above freezing. Temperature={status["temperature"]} degrees C.'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature update', message)
                self.alarms.remove(FREEZING_ALARM)
        
        if 'humidity' in message:
            logging.info(f'Humidity = {status["humidity"]}')
            self.state.humidity = float(status['humidity'])
            # check humidity value; send an alert if it rises above a preset threshold
            if self.state.is_high_humidity() and HUMIDITY_ALARM not in self.alarms:
                message = f'The basement humidity has risen to: {status["humidity"]}!'
                self.mail.send('Home humidity warning!', message)
                logging.info(f'{datetime.now()}: {message}')
                self.alarms.append(HUMIDITY_ALARM)
            # otherwise check if things are back to normal
            elif self.state.is_humidity_normal() and HUMIDITY_ALARM in self.alarms:
                message = f'The basement humidity has now fallen to: {status["humidity"]}.'
                self.mail.send('Home humidity update', message)
                logging.info(f'{datetime.now()}: {message}')
                self.alarms.remove(HUMIDITY_ALARM)

        if 'pressure' in message:
            logging.info(f'Air pressure = {status["pressure"]} hPa')
            self.state.pressure = float(status['pressure'])
