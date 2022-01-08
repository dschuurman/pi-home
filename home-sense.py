# Home-sense program to monitor and log various sensors on a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import sqlite3
from datetime import datetime
import configparser, json
import signal
import sys
import os
import logging
import paho.mqtt.client as mqtt

# GPIO and sensor libraries
import RPi.GPIO as GPIO
import busio, board
import adafruit_ahtx0

# email libraries
import smtplib
from email.utils import make_msgid
from email.mime.text import MIMEText

# CONSTANTS
PUMP_FILTER_SAMPLES = 5
VERSION = 0.1
CONFIG_FILENAME = 'home-sense.conf'
TEMPERATURE_HYSTERESIS = 1.0
HUMIDITY_HYSTERESIS = 2.0
SUMP_PUMP_INPUT_PIN = 21   # GPIO BCM input pin for sump pump float switch
MQTT_KEEPALIVE = 60
QOS = 0
# Alarms
LOW_TEMPERATURE_ALARM = 1
HUMIDITY_ALARM = 2
SUMP_PUMP_ALARM = 3

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
        except smtplib.SMTPResponseException as e:
            logging.info('{}: Email failed to send'.format(datetime.now()))
            logging.info('SMTP Error code: {} - {}'.format(e.smtp_code,e.smtp_error))
        finally:
            s.quit()

class Sensors:
    ''' Class to handle sensor related methods, data, and alarms
    '''
    def __init__(self, low_temp_threshold, high_humidity_threshold):
        ''' Constructor 
        ''' 
        # Set BCM input for float switch with pullup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SUMP_PUMP_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Create temperature/humidity sensor object for AHT20 sensor
        i2c = busio.I2C(board.SCL, board.SDA)
        self.i2c_sensor = adafruit_ahtx0.AHTx0(i2c)

        # Temp and humidity thresholds to trigger an alert
        self.LOW_TEMP_THRESHOLD = low_temp_threshold
        self.HIGH_HUMIDITY_THRESHOLD = high_humidity_threshold

    def get_temperature(self):
        return self.i2c_sensor.temperature

    def get_humidity(self):
        return self.i2c_sensor.relative_humidity

    def get_sump_pump(self):
        return GPIO.input(SUMP_PUMP_INPUT_PIN)

class Events:
    ''' Event class used to handle timer and MQTT messages
    '''
    def __init__(self, sensors, sample_period, db, email):
        ''' Constructor 
        '''
        self.sensors = sensors
        self.sample_period = sample_period
        self.email = email

        # Initialize a list to store alarms that occur
        self.alarms = []

        # initialize tick counter
        self.ticks = 0
        
        # SQL database table - create table if not found
        self.db = db
        self.db.execute('CREATE TABLE IF NOT EXISTS {} (datetime TEXT NOT NULL, temperature double NOT NULL, humidity double NOT NULL)'.format(TABLE))
        self.cursor = db.cursor()

        # Initialize a filter for sump pump sensor (note: rising edge callbacks are less reliable due to noise)
        # create filter using a list of samples over 5 intervals [x(n),x(n-1),x(n-2),x(n-3),x(n-4)]
        self.sump_samples = [0] * PUMP_FILTER_SAMPLES

    def timer_handler(self, signum, frame):
        ''' Timer signal handler- fires every second and manages sensor readings
        '''
        # first capture sensor readings
        temperature = self.sensors.get_temperature()
        humidity = self.sensors.get_humidity()
        sump = self.sensors.get_sump_pump()

        # increment tick counter
        self.ticks += 1
        logging.debug('Ticks:{} Temp:{:.2f} Humidity:{:.2f}'.format(self.ticks,temperature,humidity))

        # Insert temperature/humidity into database periodically
        if self.ticks >= self.sample_period:
            logging.debug('{}: inserting temp/humidity data into to table: {:.2f},{:.2f}'.format(datetime.now(),temperature,humidity))
            self.ticks = 0
            # Insert temp and humidity data into table
            sqlcmd = "INSERT INTO {} VALUES (datetime('now','localtime'),{:.2f},{:.2f})".format(TABLE,temperature,humidity)
            self.cursor.execute(sqlcmd)
            logging.debug("{} record inserted.".format(self.cursor.rowcount))

            # Keep just the last year of readings
            sqlcmd = "DELETE FROM {} WHERE datetime < datetime('now','localtime','-365 days')".format(TABLE)
            self.cursor.execute(sqlcmd)
            logging.debug("{} records deleted.".format(self.cursor.rowcount))
            self.db.commit()

        # Next, examine sensor values and send alerts if alarm state changes

        # Check sump switch:
        # store samples in a list of last n samples
        # if last n samples are high send an alert
        self.sump_samples = [sump] + self.sump_samples[0:-1]
        if all(self.sump_samples) and SUMP_PUMP_ALARM not in self.alarms:
            message = 'SUMP PUMP ALARM: {}'.format(datetime.now())
            logging.info(message)
            self.email.send("SUMP PUMP ALARM!", message)
            self.alarms.append(SUMP_PUMP_ALARM)
        # if last n samples are low, turn off alarm if it is on
        elif not any(self.sump_samples) and SUMP_PUMP_ALARM in self.alarms:
            message = 'Sump pump sensor returned to normal: {}'.format(datetime.now())
            logging.info(message)
            self.email.send("Sump pump returned to normal", message)
            self.alarms.remove(SUMP_PUMP_ALARM)

        # Next, check temperature value; send an alert if it falls below a preset threshold
        if temperature < sensors.LOW_TEMP_THRESHOLD:
            if LOW_TEMPERATURE_ALARM not in self.alarms:
                message = "The house temperature has fallen to: {} degrees C!".format(temperature)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.email.send('Home temperature warning!', message)
                self.alarms.append(LOW_TEMPERATURE_ALARM)
            # Turn flag off - with hysteresis
            elif temperature > sensors.LOW_TEMP_THRESHOLD + TEMPERATURE_HYSTERESIS:
                message = "The house temperature is now risen to {} degrees C.".format(temperature)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.email.send('Home temperature update', message)
                self.alarms.remove(LOW_TEMPERATURE_ALARM)

        # Next, check humidity value; send an alert if it rises above a preset threshold
        if humidity > sensors.HIGH_HUMIDITY_THRESHOLD:
            if HUMIDITY_ALARM not in self.alarms:
                message = "The basement humidity has risen to: {}%!".format(humidity)
                self.email.send('Home humidity warning!', message)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.alarms.append(HUMIDITY_ALARM)
            # Turn flag off - with hysteresis
            elif humidity < sensors.HIGH_HUMIDITY_THRESHOLD - HUMIDITY_HYSTERESIS:
                message = "The basement humidity has now fallen to: {}%.".format(humidity)
                self.email.send('Home humidity update', message)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.alarms.remove(HUMIDITY_ALARM)

    def mqtt_message_handler(self, client, data, msg):
        ''' MQTT message handler
            Send e-mail alert when water leak or low battery detected
        '''
        message = str(msg.payload.decode("utf-8"))
        status = json.loads(message) # Parse JSON message from sensor
        logging.info('Message received {}: {}'.format(datetime.now(), message))
        water_sensor = msg.topic.split('/')[1]   # Extract sensor "friendly name" from MQTT topic
        
        if status['water_leak'] and water_sensor not in self.alarms:
            self.email.send("Water lealk alarm detected for {}!".format(water_sensor), message)
            logging.info('Water lealk alarm detected for {}!'.format(water_sensor))
            self.alarms.append(water_sensor)
        elif not status['water_leak'] and water_sensor in self.alarms:
            self.email.send("Water lealk alarm stopped for {}".format(water_sensor), message)
            logging.info('Water lealk alarm stopped for {}!'.format(water_sensor))
            self.alarms.remove(water_sensor)
        if status['battery_low'] == True:
            self.email.send('Low battery detected on {}!'.format(water_sensor), message)
            logging.info('Low battery detected on {}!'.format(water_sensor))

def sigint_handler(signum, frame):
    ''' SIGINT handler - exit gracefully
    '''
    global db
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    db.close()                                   # close db
    logging.info('Program recevied SIGINT at: {}'.format(datetime.now()))
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
    print('Missing parameter in configuration file: {}'.format(e))
    sys.exit(os.EX_CONFIG)

# Configuration settings with fallback values
BROKER_IP = conf.get('home-sense', 'broker_ip', fallback="127.0.0.1")
BROKER_PORT = conf.getint('home-sense', 'broker_port', fallback=1883)
WATER_SENSORS = json.loads(conf.get('home-sense', 'water_sensors', fallback=[]))
DATABASE = conf.get('home-sense', 'database', fallback='/home/pi/sensor_data.db')
LOG_FILE = conf.get('home-sense', 'logfile', fallback='/tmp/home-sense.log')
TABLE = conf.get('home-sense', 'table', fallback='TemperatureHumidity')
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
logging.info('Starting at {} with version {}'.format(datetime.now(),VERSION))

# setup a sigint handler to terminate gracefully
signal.signal(signal.SIGINT, sigint_handler)

# Connect to the sqlite database
db = sqlite3.connect(DATABASE)

# Instantiate a sensor object for temperature, humidity, sump pump, and water leaks
sensors = Sensors(LOW_TEMP_THRESHOLD, HIGH_HUMIDITY_THRESHOLD)

# Instantiate an e-mail object for alerts
email = Email(SENDER_EMAIL, RECIPIENT_EMAIL, SMTP_SERVER)

# Creation timer object with 1 second timer
events = Events(sensors,SAMPLE_PERIOD,db,email)
signal.signal(signal.SIGALRM, events.timer_handler)
signal.setitimer(signal.ITIMER_REAL, 1, 1)

# Connect to MQTT broker and subscribe to all water leak sensors
client = mqtt.Client()
ret = client.connect(BROKER_IP, BROKER_PORT, MQTT_KEEPALIVE)
if ret != 0:
    logging.error('MQTT connect return code: {}'.format(ret))
client.on_message = events.mqtt_message_handler
for sensor in WATER_SENSORS:
    client.subscribe("zigbee2mqtt/{}".format(sensor), qos=QOS)
    logging.info('Subscribed to {}'.format(sensor))

# Loop forever waiting for events
try:
    client.loop_forever()
except KeyboardInterrupt:
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    client.disconnect()
    db.close()
    logging.info('Terminating due to KeyboardInterrupt.')
