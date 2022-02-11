# Home-sense program for use with Zigbee devices and a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from distutils.log import debug
from datetime import datetime
import configparser
import signal
import sys
import os
import logging
from telnetlib import SE
import paho.mqtt.client as mqtt

# Custom classes
from events import Events
from state import State
from mail import Mail
from flaskthread import FlaskThread

# CONSTANTS
VERSION = 0.3
CONFIG_FILENAME = 'home-sense.conf'
TIMER_PERIOD = 300
TABLE = 'SensorData'
MQTT_KEEPALIVE = 60
QOS = 0

def sigint_handler(signum, frame):
    ''' SIGINT handler - exit gracefully
    '''
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    logging.info(f'Program recevied SIGINT at: {datetime.now()}')
    logging.shutdown()
    sys.exit(0)

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
    for i in range(len(SENSORS)):
        SENSORS[i] = SENSORS[i].strip()
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
mail = Mail(SENDER_EMAIL, RECIPIENT_EMAIL, SMTP_SERVER)

# Create an event handling object
events = Events(state, DATABASE, mail)
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
    server = FlaskThread(WEB_SERVER_PORT, DATABASE)
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
