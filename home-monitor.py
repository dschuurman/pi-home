# Home monitor script to monitor various sensors running on a Raspberry Pi
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import sqlite3
from datetime import datetime
import configparser
import signal
import sys
import os
import logging

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
CONFIG_FILENAME = 'home-monitor.conf'
TEMPERATURE_HYSTERESIS = 1.0
HUMIDITY_HYSTERESIS = 2.0

## Function definitions ###

class Email:
    ''' Class to encapsulate methods to send an alert email
        Assumes an SMTP server is available.
    '''
    def __init__(self,from_address, to_address, server):
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
            # creates SMTP session and sends mail
            s = smtplib.SMTP(self.server)
            s.sendmail(self.from_address, self.to_address, msg.as_string())
        except smtplib.SMTPResponseException as e:
            logging.info('{}: Email failed to send'.format(datetime.now()))
            logging.info('SMTP Error code: {} - {}'.format(e.smtp_code,e.smtp_error))
        finally:
            s.quit()

class Sensors:
    ''' Class to store sensor related methods and data
    '''
    def __init__(self, sump_pump_input_pin, low_temp_threshold, high_humidity_threshold):
        ''' Constructor 
        ''' 
        # Set BCM input for float switch with pullup
        self.sump_pump_input_pin = sump_pump_input_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(sump_pump_input_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Create temperature/humidity sensor object for AHT20 sensor
        i2c = busio.I2C(board.SCL, board.SDA)
        self.sensor = adafruit_ahtx0.AHTx0(i2c)

        # Temp and humidity thresholds to trigger an alert
        self.LOW_TEMP_THRESHOLD = low_temp_threshold
        self.HIGH_HUMIDITY_THRESHOLD = high_humidity_threshold

    def get_temperature(self):
        return self.sensor.temperature

    def get_humidity(self):
        return self.sensor.relative_humidity

    def get_sump_pump(self):
        return GPIO.input(self.sump_pump_input_pin)


class Timer:
    ''' Timer class used to control periodic actions with one tick per second
    '''
    def __init__(self, sensors, sample_period, db, email):
        ''' Constructor 
        '''
        self.sensors = sensors
        self.sample_period = sample_period

        # flags to indicate when temp and humidity have passed a threshold
        self.low_temp_flag = False
        self.high_humidity_flag = False
        self.sump_alarm = False
        self.email = email

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

        # Next, examine sensor values and send alerts as needed

        # Check sump switch:
        # store samples in a list of last n samples
        # if last n samples are high send an alert
        self.sump_samples = [sump] + self.sump_samples[0:-1]
        if all(self.sump_samples) and not self.sump_alarm:
            self.sump_alarm = True
            message = 'SUMP PUMP ALARM: {}'.format(datetime.now())
            logging.info(message)
            self.email.send("SUMP PUMP ALARM!", message)
        # if last n samples are low, turn off alarm if it is on
        elif not any(self.sump_samples) and self.sump_alarm:
            self.sump_alarm = False
            message = 'Sump pump sensor returned to normal: {}'.format(datetime.now())
            logging.info(message)
            self.email.send("Sump pump returned to normal", message)

        # Next, check temperature value; send an alert if it falls below a preset threshold
        if temperature < sensors.LOW_TEMP_THRESHOLD:
            if not self.low_temp_flag:
                message = "The house temperature has fallen to: {} degrees C!".format(temperature)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.email.send('Home temperature warning!', message)
                self.low_temp_flag = True
            # Turn flag off - with hysteresis
            elif temperature > sensors.LOW_TEMP_THRESHOLD + TEMPERATURE_HYSTERESIS:
                message = "The house temperature is now risen to {} degrees C.".format(temperature)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.email.send('Home temperature update', message)
                self.low_temp_flag = False

        # Next, check humidity value; send an alert if it rises above a preset threshold
        if humidity > sensors.HIGH_HUMIDITY_THRESHOLD:
            if not self.high_humidity_flag:
                message = "The basement humidity has risen to: {}%!".format(humidity)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.email.send('Home humidity warning!', message)
                self.high_humidity_flag = True
            # Turn flag off - with hysteresis
            elif humidity < sensors.HIGH_HUMIDITY_THRESHOLD - HUMIDITY_HYSTERESIS:
                message = "The basement humidity has now fallen to: {}%.".format(humidity)
                logging.info('{}: {}'.format(datetime.now(),message))
                self.email.send('Home humidity update', message)
                self.high_humidity_flag = False


def sigint_handler(signum, frame):
    ''' SIGINT handler - exit gracefully
    '''
    global db
    db.close()                                   # close db
    signal.setitimer(signal.ITIMER_REAL, 0, 0)   # Disable interval timer
    logging.info('Program recevied SIGINT at: {}'.format(datetime.now()))
    logging.shutdown()
    sys.exit(0)

# ------------ main program starts here ---------------

# Read settings from configuration file
conf = configparser.ConfigParser()
conf.read(os.path.join(os.path.abspath(os.path.dirname(__file__)), CONFIG_FILENAME))
try:
    SENDER_EMAIL = conf.get('home-monitor', 'sender_email')
    RECIPIENT_EMAIL = conf.get('home-monitor', 'recipient_email')
    SMTP_SERVER = conf.get('home-monitor', 'smtp_server')
    SUMP_PUMP_INPUT_PIN = conf.getint('home-monitor', 'sump_pump_input_pin')
except configparser.NoOptionError as e:
    print('Missing parameter in configuration file: {}'.format(e))
    sys.exit(os.EX_CONFIG)

DATABASE = conf.get('home-monitor', 'database', fallback='/home/pi/sensor_data.db')
LOG_FILE = conf.get('home-monitor', 'logfile', fallback='/tmp/home-monitor.log')
TABLE = conf.get('home-monitor', 'table', fallback='TemperatureHumidity')
LOW_TEMP_THRESHOLD = conf.getfloat('home-monitor', 'low_temp_threshold', fallback=10.0)
HIGH_HUMIDITY_THRESHOLD = conf.getfloat('home-monitor', 'high_humidity_threshold', fallback=85.0)
SAMPLE_PERIOD = conf.getint('home-monitor', 'sample_period', fallback=300)
LOG_LEVEL = conf.get('home-monitor', 'loglevel', fallback='info')

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

# Instantiate a sensor object
sensors = Sensors(SUMP_PUMP_INPUT_PIN, LOW_TEMP_THRESHOLD, HIGH_HUMIDITY_THRESHOLD)

# Instantiate an e-mail object for alerts
email = Email(SENDER_EMAIL, RECIPIENT_EMAIL, SMTP_SERVER)

# Creation timer object with 1 second timer
timer = Timer(sensors,SAMPLE_PERIOD,db,email)
signal.signal(signal.SIGALRM, timer.timer_handler)
signal.setitimer(signal.ITIMER_REAL, 1, 1)

# Continuously loop blocking on timer signal
while True:
    signal.pause()      # block until periodic timer fires, then repeat
