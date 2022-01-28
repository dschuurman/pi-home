# Home-sense program to monitor and log various sensors on a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from distutils.log import debug
import sqlite3
from datetime import datetime
import math
import configparser
import signal
import sys
import os
import logging
import paho.mqtt.client as mqtt
import json
from threading import Thread
from flask import Flask, render_template, request
from waitress import serve

# email libraries
import smtplib
from email.utils import make_msgid
from email.mime.text import MIMEText

# CONSTANTS
VERSION = 0.3
CONFIG_FILENAME = 'home-sense.conf'
TIMER_PERIOD = 300
TABLE = 'SensorData'
NUMBER_OF_PLOT_POINTS = 1000
TEMPERATURE_HYSTERESIS = 1.0
HUMIDITY_HYSTERESIS = 2.0
MQTT_KEEPALIVE = 60
QOS = 0

# Alarm codes
LOW_TEMPERATURE_ALARM = 1
FREEZING_ALARM = 2
HUMIDITY_ALARM = 3

## Class definitions ###

class Email:
    ''' Class to encapsulate methods to send an alert email
        Assumes an SMTP server is available.
    '''
    def __init__(self, from_address, to_address, server):
        ''' Function to send a warning email - assumes server running locally to forward mail
        '''
        self.to_address = to_address        
        self.from_address = from_address
        self.server = server

    def send(self, subject, message):
        ''' Function to send an email - requires SMTP server to forward mail
        '''
        # message to be sent
        msg = MIMEText(message)
        msg['To'] = self.to_address
        msg['From'] = self.from_address
        msg['Subject'] = subject
        msg['Message-ID'] = make_msgid()

        # send the mail and terminate the session
        try:
            # creates SMTP session and send mail
            s = smtplib.SMTP(self.server)
            s.sendmail(self.from_address, self.to_address, msg.as_string())
            logging.info(f'{datetime.now()}: Email alert sent to {self.to_address}')
        except smtplib.SMTPResponseException as e:
            logging.info(f'{datetime.now()}: Email failed to send')
            logging.info(f'SMTP Error code: {e.smtp_code} - {e.smtp_error}')
        finally:
            s.quit()

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
    

class Events:
    ''' Event class used to handle timer and MQTT messages
    '''
    def __init__(self, state, database, email):
        ''' Constructor 
        '''
        self.state = state
        self.email = email

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
                self.email.send(f'Water leak alarm detected for {sensor}!',message)
                logging.info(f'Water leak alarm detected for {sensor}!')
                self.alarms.append(sensor)
                self.state.water_leak = True
            elif not status['water_leak'] and sensor in self.alarms:
                self.email.send(f'Water leak alarm stopped for {sensor}',message)
                logging.info(f'Water leak alarm stopped for {sensor}!')
                self.alarms.remove(sensor)
                self.state.water_leak = False

        if 'battery_low' in message and status['battery_low']:
            self.email.send(f'Low battery detected for {sensor}!', message)
            logging.info(f'Low battery detected for {sensor}!')

        if 'temperature' in message:
            logging.info(f'Temperature = {status["temperature"]} degrees C')
            self.state.temperature = float(status['temperature'])
            # Next, check temperature value; send an alert if it falls below a preset threshold
            if state.is_low_temp() and LOW_TEMPERATURE_ALARM not in self.alarms:
                message = f'The house temperature has fallen to: {status["temperature"]} degrees C!'
                logging.info(f'{datetime.now()}: {message}')
                self.email.send('Home temperature warning!', message)
                self.alarms.append(LOW_TEMPERATURE_ALARM)
            # otherwise check if temperature returns back above threshold
            elif state.is_temp_normal() and LOW_TEMPERATURE_ALARM in self.alarms:
                message = f'The house temperature is now risen to {status["temperature"]} degrees C.'
                logging.info(f'{datetime.now()}: {message}')
                self.email.send('Home temperature update', message)
                self.alarms.remove(LOW_TEMPERATURE_ALARM)
            # check explicitly for freezing temperatures
            elif state.is_freezing() and FREEZING_ALARM not in self.alarms:
                message = f'The house temperature is freezing! Temperature={status["temperature"]} degrees C!'
                logging.info(f'{datetime.now()}: {message}')
                self.email.send('Home temperature FREEZING!', message)
                self.alarms.append(FREEZING_ALARM)
            # otherwise check if things are no longer freezing
            elif state.is_above_freezing() and FREEZING_ALARM in self.alarms:
                message = f'The house temperature is now risen above freezing. Temperature={status["temperature"]} degrees C.'
                logging.info(f'{datetime.now()}: {message}')
                self.email.send('Home temperature update', message)
                self.alarms.remove(FREEZING_ALARM)
        
        if 'humidity' in message:
            logging.info(f'Humidity = {status["humidity"]}')
            self.state.humidity = float(status['humidity'])
            # check humidity value; send an alert if it rises above a preset threshold
            if state.is_high_humidity() and HUMIDITY_ALARM not in self.alarms:
                message = f'The basement humidity has risen to: {status["humidity"]}!'
                self.email.send('Home humidity warning!', message)
                logging.info(f'{datetime.now()}: {message}')
                self.alarms.append(HUMIDITY_ALARM)
            # otherwise check if things are back to normal
            elif state.is_humidity_normal() and HUMIDITY_ALARM in self.alarms:
                message = f'The basement humidity has now fallen to: {status["humidity"]}.'
                self.email.send('Home humidity update', message)
                logging.info(f'{datetime.now()}: {message}')
                self.alarms.remove(HUMIDITY_ALARM)

        if 'pressure' in message:
            logging.info(f'Air pressure = {status["pressure"]} hPa')
            self.state.pressure = float(status['pressure'])

class FlaskThread(Thread):
    ''' Class definition to run flask to provide web pages to display sensor data
    '''
    def __init__(self, port, database):
        self.port = port
        self.database = database
        Thread.__init__(self)

        # Create a flask object and initialize web pages
        self.app = Flask(__name__)
        self.app.debug = True
        self.app.add_url_rule('/', 'chart', self.chart)

    def run(self):
        # Start the waitress WSGI server on the specified port
        serve(self.app, host='0.0.0.0', port=self.port)

    # Methods for each flask webpage route
    def chart(self):
        ''' Returns chart.html webpage
        '''
        self.db = sqlite3.connect(self.database)
        self.cursor = self.db.cursor()
        day_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-1 day')").fetchall()

        count = self.cursor.execute(f"SELECT COUNT(*) FROM {TABLE} where datetime > datetime('now','localtime','-30 day')").fetchone()[0]
        skip = math.ceil(count/NUMBER_OF_PLOT_POINTS)  # Number of rows to skip over for each point to ensure number of plot points stays reasonable
        month_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-30 day') AND ROWID % {skip} = 0").fetchall()

        count = self.cursor.execute(f"SELECT COUNT(*) FROM {TABLE} where datetime > datetime('now','localtime','-365 day')").fetchone()[0]
        skip = math.ceil(count/NUMBER_OF_PLOT_POINTS)  # Number of rows to skip over for each point to ensure number of plot points stays reasonable
        year_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-365 day') AND ROWID % {skip} = 0").fetchall()
        return render_template('chart.html', day_data=day_data, month_data=month_data, year_data=year_data)

def sigint_handler(signum, frame):
    ''' SIGINT handler - exit gracefully
    '''
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    logging.info(f'Program recevied SIGINT at: {datetime.now()}')
    logging.shutdown()
    sys.exit(0)

# ------------ main program starts here ---------------

# Read settings from configuration file
conf = configparser.ConfigParser()
conf.read(os.path.join(os.path.abspath(os.path.dirname(__file__)), CONFIG_FILENAME))
try:
    SENDER_EMAIL = conf.get('home-sense', 'sender_email')
    RECIPIENT_EMAIL = conf.get('home-sense', 'recipient_email')
    SMTP_SERVER = conf.get('home-sense', 'smtp_server')
except configparser.NoOptionError as e:
    print(f'Missing parameter in configuration file: {e}')
    sys.exit(os.EX_CONFIG)

# Configuration settings with fallback values
BROKER_IP = conf.get('home-sense', 'broker_ip', fallback="127.0.0.1")
BROKER_PORT = conf.getint('home-sense', 'broker_port', fallback=1883)
SENSORS = conf.get('home-sense', 'sensors', fallback=None)
if SENSORS != None:
    SENSORS = SENSORS.split(',')
DATABASE = conf.get('home-sense', 'database', fallback='/home/pi/sensor_data.db')
WEB_SERVER_PORT = conf.getint('home-sense', 'web_server_port', fallback=8080)
WEB_INTERFACE = conf.getboolean('home-sense', 'web_interface',fallback=False)
LOG_FILE = conf.get('home-sense', 'logfile', fallback='/tmp/home-sense.log')
LOW_TEMP_THRESHOLD = conf.getfloat('home-sense', 'low_temp_threshold', fallback=10.0)
HIGH_HUMIDITY_THRESHOLD = conf.getfloat('home-sense', 'high_humidity_threshold', fallback=85.0)
SAMPLE_PERIOD = conf.getint('home-sense', 'sample_period', fallback=300)
LOG_LEVEL = conf.get('home-sense', 'loglevel', fallback='info')

# Start logging and set logging level; default to INFO level
if LOG_LEVEL == 'error':
    logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, filemode='w')
elif LOG_LEVEL == 'debug':
    logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, filemode='w')
else:
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO, filemode='w')

# Start log file
logging.info(f'Starting at {datetime.now()} with version {VERSION} loglevel={LOG_LEVEL}')

# setup a sigint handler to terminate gracefully
signal.signal(signal.SIGINT, sigint_handler)

# Instantiate a state object to track state of sensor values
state = State(SENSORS, LOW_TEMP_THRESHOLD, HIGH_HUMIDITY_THRESHOLD)

# Instantiate an e-mail object for sending alerts
email = Email(SENDER_EMAIL, RECIPIENT_EMAIL, SMTP_SERVER)

# Create an event handling object
events = Events(state,DATABASE,email)
signal.signal(signal.SIGALRM, events.timer_handler)
signal.setitimer(signal.ITIMER_REAL, TIMER_PERIOD, TIMER_PERIOD)

# Connect to MQTT broker and subscribe to all water leak sensors
client = mqtt.Client()
ret = client.connect(BROKER_IP, BROKER_PORT, MQTT_KEEPALIVE)
if ret != 0:
    logging.error(f'MQTT connect return code: {ret}')
client.on_message = events.mqtt_message_handler
logging.info(f'MQTT client connected to {BROKER_IP} on port {BROKER_PORT}')

# Subscribe to all zigbee sensors
for sensor in SENSORS:
    client.subscribe(f'zigbee2mqtt/{sensor}', qos=QOS)
    logging.info(f'Subscribed to: {sensor}')

# If web interface is enabled, start the flask web server in a separate thread
if WEB_INTERFACE:
    logging.info('Web interface ENABLED')
    server = FlaskThread(WEB_SERVER_PORT,DATABASE)
    server.start()
else:
    logging.info('Web interface DISABLED')

# Loop forever waiting for events
try:
    client.loop_forever()
except KeyboardInterrupt:
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    client.disconnect()
    logging.info('Terminating due to KeyboardInterrupt.')
