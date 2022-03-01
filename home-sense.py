# Home-sense program for use with Zigbee home lights and sensors and a Raspberry Pi
# (C) 2020,2021,2022 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from datetime import datetime
import configparser
import signal
import sched, time
import sys
import os
import logging
from telnetlib import SE
import paho.mqtt.client as mqtt
from astral.sun import sun
from astral.geocoder import lookup, database
from waitress import serve

# Custom classes
from sensors import Sensors, Events, Mail
from flaskthread import FlaskThread
from lights import Lights

# CONSTANTS
VERSION = 0.5
CONFIG_FILENAME = 'home-sense.conf'
TABLE = 'SensorData'
MQTT_KEEPALIVE = 60
QOS = 0

def sigint_handler(signum, frame):
    ''' SIGINT handler - exit gracefully
    '''
    #signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    logging.info(f'Program recevied SIGINT at: {datetime.now()}')
    logging.shutdown()
    sys.exit(0)

# Read settings from configuration file (located in the same folder as the program)
conf = configparser.ConfigParser()
conf.read(os.path.join(os.path.abspath(os.path.dirname(__file__)), CONFIG_FILENAME))

# Configuration settings with fallback values
BROKER_IP = conf.get('home-sense', 'broker_ip', fallback="127.0.0.1")
BROKER_PORT = conf.getint('home-sense', 'broker_port', fallback=1883)
SENSORS = conf.get('home-sense', 'sensors', fallback=None)
if SENSORS != None:
    SENSORS = SENSORS.split(',')
    for i in range(len(SENSORS)):
        SENSORS[i] = SENSORS[i].strip()
BULBS = conf.get('home-sense', 'bulbs', fallback=None)
if BULBS != None:
    BULBS = BULBS.split(',')
    for i in range(len(BULBS)):
        BULBS[i] = BULBS[i].strip()
OUTLETS = conf.get('home-sense', 'outlets', fallback=None)
if OUTLETS != None:
    OUTLETS = OUTLETS.split(',')
    for i in range(len(OUTLETS)):
        OUTLETS[i] = OUTLETS[i].strip()
BRIGHTNESS = conf.getint('home-sense', 'brightness',fallback=254)
OFF_TIME = conf.get('home-sense', 'off_time',fallback='23:00')
DATABASE = conf.get('home-sense', 'database', fallback='/home/pi/sensor_data.db')
WEB_SERVER_PORT = conf.getint('home-sense', 'web_server_port', fallback=8080)
WEB_INTERFACE = conf.getboolean('home-sense', 'web_interface',fallback=False)
CITY = conf.get('home-sense', 'city',fallback='Detroit')
LOG_FILE = conf.get('home-sense', 'logfile', fallback='/tmp/home-sense.log')
LOW_TEMP_THRESHOLD = conf.getfloat('home-sense', 'low_temp_threshold', fallback=10.0)
HIGH_HUMIDITY_THRESHOLD = conf.getfloat('home-sense', 'high_humidity_threshold', fallback=85.0)
SAMPLE_PERIOD = conf.getint('home-sense', 'sample_period', fallback=300)
SENDER_EMAIL = conf.get('home-sense', 'sender_email', fallback='')
RECIPIENT_EMAIL = conf.get('home-sense', 'recipient_email', fallback='')
SMTP_SERVER = conf.get('home-sense', 'smtp_server', fallback='')
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

# Check configuration settings
# Check brightness value
if not (0 <= BRIGHTNESS <=254):
    logging.error(f'Invalid brightness setting in configuration file: {BRIGHTNESS} -  setting default (254)')
    BRIGHTNESS = 254
else:
    logging.info(f'Brightness settting: {BRIGHTNESS}')
# Check city setting
try:
    lookup(CITY, database())
except KeyError:
    logging.error(f'Unrecognized city in configuration file: {CITY}')
# Check off-time setting
if not ((':' in OFF_TIME) and (4 <= len(OFF_TIME) <= 5) and (0 <= int(OFF_TIME.split(':')[0]) < 24) and (0 <= int(OFF_TIME.split(':')[1])<60)):
    logging.error(f'Invalid off_time in conf file {OFF_TIME} - using default off-time 23:00')
    OFF_TIME = "23:00"
# Set default lights off-time for today
lights_out_time = datetime.now().replace(hour=int(OFF_TIME.split(':')[0]), minute=int(OFF_TIME.split(':')[1]))
logging.info(f'Default lights OFF time set to: {lights_out_time.strftime("%H:%M")}')

# setup a sigint handler to exit gracefully on signal
signal.signal(signal.SIGINT, sigint_handler)

# Instantiate a sensor object to track state of sensor values
sensors = Sensors(SENSORS, LOW_TEMP_THRESHOLD, HIGH_HUMIDITY_THRESHOLD)

# Create scheduler to control lights and periodically sample sensors
# Set delayfunc to run with (at most) 1 second sleep so that it can periodically wake up to adjust 
# to any changes to the scheduler queue (which can occur in the flask thread)
scheduler = sched.scheduler(time.time, delayfunc=lambda time_to_sleep: time.sleep(min(1, time_to_sleep)))

# Create an event handling object with e-mail alerts
mail = Mail(SENDER_EMAIL, RECIPIENT_EMAIL, SMTP_SERVER)
events = Events(scheduler, sensors, DATABASE, mail)

# set up periodic timer event for logging sensor data
scheduler.enter(10, 1, events.timer_event)

# Connect to MQTT broker provided by zigbee2mqtt
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

# Create an object to control lights with smart bulbs and smart outlets
lights = Lights(BULBS, OUTLETS, BRIGHTNESS, scheduler, client, CITY, lights_out_time)

# Start a flask web server in a separate thread
logging.info('Starting web interface...')
server = FlaskThread(WEB_SERVER_PORT, lights, sensors, DATABASE, LOG_FILE, VERSION)
server.start()

# Loop forever waiting for events
try:
    client.loop_start()
    scheduler.run()
except KeyboardInterrupt:
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    client.disconnect()
    logging.info('Terminating due to KeyboardInterrupt.')
