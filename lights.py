# Home Automation script for Zigbee lights, sockets, and sensors to run on Raspberry Pi
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import sys, os
import paho.mqtt.client as mqtt
import logging
import configparser
from datetime import date, datetime, timezone, timedelta
from astral.sun import sun
from astral.geocoder import lookup, database
from threading import Thread, Lock
from flask import Flask, render_template, request
from waitress import serve
import signal
import sched, time

# Constants
MQTT_KEEPALIVE = 60

#### Class definitions ####

class Lights:
    ''' Lights class used to schedule and control lights
        using smart bulbs and smart outlets
    '''
    def __init__(self, bulbs, outlets, brightness, scheduler, client, city):
        ''' Constructor 
        '''
        self.scheduler = scheduler
        self.client = client
        self.city = city

        # Set default lights on and off times
        self.lights_out_hour = 23
        self.lights_out_minute = 59
        self.lights_out_hour = 18
        self.lights_out_minute = 00

        # Store bulbs, outlets, and brightness settings
        self.bulbs = bulbs
        self.outlets = outlets
        self.set_brightness(brightness)
        logging.info(f'Devices: {bulbs},{outlets}')

        # Initialize timer control of lights to be enabled (normally used for porch lights)
        self.bulb_timer = True

        # Initialize timer control of outlets to be disabled (normally used for vacation)
        self.outlet_timer = False

        # Use a mutex for thread synchronization
        self.lock = Lock()

        # Set lights on-time to dusk by default
        self.on_time_mode = 'dusk'      # mode is either set to "dusk" or "fixed"
        lights_on_time = self.get_next_dusk_time()
        today = datetime.now().date()
        lights_on_time = lights_on_time.replace(year=today.year, month=today.month, day=today.day)

        # Set lights out time to 11:59pm by default
        self.off_time_mode = 'fixed'    # mode is either set to "dawn" or "fixed"

        # Initialize lights and schedule events
        self.bulb_state = False
        self.outlet_state = False
        # If current time is between lights ON and OFF then set lights ON and schedule event for OFF time
        if lights_on_time <= datetime.now() < lights_out_time:
            self.lights_on()
        # Otherwise turn lights OFF and schedule event to turn lights ON at next dusk time
        else:
            self.lights_off()

    def lights_on(self):
        ''' turn lights on and schedule next event to turn lights off
        '''
        logging.info(f'*** Turning lights ON at {datetime.now().strftime("%m/%d/%Y %H:%M:%S")} ***')
        self.turn_on_bulbs()

        # If outlets are enabled then turn them on as well
        if self.outlet_timer:
            logging.info(f'*** Turning outlets ON at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")} ***')
            self.turn_on_outlets()

        # set next lights off time
        logging.info(f'Next event = Lights OFF at: {self.get_next_lights_out_time().strftime("%m/%d/%Y, %H:%M:%S")}')
        seconds = round((self.get_next_lights_out_time() - datetime.now()).total_seconds())
        self.scheduler.enter(seconds, 1, self.lights_off)

    def lights_off(self):
        ''' turn lights off and schedule next event to turn lights on
        '''
        logging.info(f'*** Turning lights OFF at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")} ***')
        self.turn_off_bulbs()

        # If outlets are enabled then turn them off as well
        if self.outlet_timer:
            logging.info(f'*** Turning outlets OFF at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")} ***')
            self.turn_off_outlets()       

        # set next lights on time
        logging.info(f'Next event = Lights ON at: {self.get_next_lights_on_time().strftime("%m/%d/%Y, %H:%M:%S")}')
        seconds = round((self.get_next_lights_on_time() - datetime.now()).total_seconds())
        self.scheduler.enter(seconds, 1, self.lights_on)

    def set_lights_on_time(self, hour, minute):
        ''' Set lights on time
        '''
        # Update new lights on time
        self.lights_on_hour = hour
        self.lights_on_minute = minute
        logging.info(f'Lights ON time changed to: {self.lights_on_hour}:{self.lights_on_minute:02}')

        # Search scheduler queue to remove current light event before inserting new one
        for event in self.scheduler.queue:
            if event.action == self.lights_off or event.action == self.lights_on:
                self.scheduler.cancel(event)   # Purge old event from the queue
        # If lights should now be on: turn them on (and add next event to the queue)
        if datetime.now() < self.get_next_lights_out_time() < self.get_next_dusk_time():
            self.lights_on()
        else:   # Otherwise turn lights off (and add the next event to the queue)
            self.lights_off()

    def set_lights_out_time(self, hour, minute):
        ''' Set lights out time
        '''
        # Update new lights out time
        self.lights_out_hour = hour
        self.lights_out_minute = minute
        logging.info(f'Lights out time changed to: {self.lights_out_hour}:{self.lights_out_minute:02}')

        # Search scheduler queue to remove current light event before inserting new one
        for event in self.scheduler.queue:
            if event.action == self.lights_off or event.action == self.lights_on:
                self.scheduler.cancel(event)   # Purge old event from the queue
        # If lights should now be on: turn them on (and add next event to the queue)
        if datetime.now() < self.get_next_lights_out_time() < self.get_next_dusk_time():
            self.lights_on()
        else:   # Otherwise turn lights off (and add the next event to the queue)
            self.lights_off()

    def get_next_lights_on_time(self):
        ''' Get next lights on time
        '''
        if self.on_time_mode == 'fixed':
            lights_on_time = datetime.now().replace(hour=self.lights_on_hour, minute=self.lights_on_minute, second=0)
            # If lights on time has already passed for today, return lights on time for tomorrow
            if lights_on_time < datetime.now():
                lights_on_time += timedelta(days=1)
        else:
            # if lights on time is not fixed, then set to next dusk time
            lights_on_time = self.get_next_dusk_time()
        return lights_on_time

    def get_next_lights_out_time(self):
        ''' Get next lights out time
        '''
        if self.off_time_mode == 'fixed':
            lights_out_time = datetime.now().replace(hour=self.lights_out_hour, minute=self.lights_out_minute, second=0)
            # If lights out time has already passed for today, return lights out time for tomorrow
            if lights_out_time < datetime.now():
                lights_out_time += timedelta(days=1)
        else:
            # if lights out time is not fixed, then set to next dawn time
            lights_out_time = self.get_next_dawn_time()
        return lights_out_time

    def get_next_dusk_time(self):
        ''' Determine next dusk time for local city
        '''
        try:
            city = lookup(self.city, database())
        except KeyError:         # Log error and return 5PM by default if city not found
            logging.error(f'Unrecognized city {self.city}, using default dusk time of 5PM.')
            return datetime.today().replace(hour=17, minute=0)
        # Compute dusk time for today (corresponding to a solar depression angle of 6 degrees)
        s = sun(city.observer, tzinfo=city.timezone)
        dusk = s['dusk']
        dusk = dusk.replace(tzinfo=None)  # remove timezone to be compatible with datetime

        # If dusk time has already passed for today, return next dusk time for tomorrow
        if dusk < datetime.now():
            s = sun(city.observer, tzinfo=city.timezone, date=date.today()+timedelta(days=1))
            dusk = s['dusk']
            dusk = dusk.replace(tzinfo=None)
        return dusk

    def get_next_dawn_time(self):
        ''' Determine next dawn time for local city
        '''
        try:
            city = lookup(self.city, database())
        except KeyError:         # Log error and return 5PM by default if city not found
            logging.error(f'Unrecognized city {self.city}, using default dusk time of 5PM.')
            return datetime.today().replace(hour=17, minute=0)
        # Compute dusk time for today (corresponding to a solar depression angle of 6 degrees)
        s = sun(city.observer, tzinfo=city.timezone)
        dawn = s['dawn']
        dawn = dawn.replace(tzinfo=None)  # remove timezone to be compatible with datetime

        # If dusk time has already passed for today, return next dusk time for tomorrow
        if dawn < datetime.now():
            s = sun(city.observer, tzinfo=city.timezone, date=date.today()+timedelta(days=1))
            dusk = s['dawn']
            dusk = dusk.replace(tzinfo=None)
        return dawn

    def turn_on_bulbs(self):
        ''' Method to turn on all bulbs
        '''
        self.lock.acquire()
        for bulb in self.bulbs:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{bulb}/set/state', 'ON')
            if rc != 0:
                logging.error(f'MQTT publish return codes: {rc}')
        self.bulb_state = True
        self.lock.release()
        logging.debug('Lights turned on')

    def turn_off_bulbs(self):
        ''' Method to turn off all bulbs
        '''
        self.lock.acquire()
        for bulb in self.bulbs:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{bulb}/set/state', 'OFF')
            if rc != 0:
                logging.error(f'MQTT publish return code: {rc}')       
        self.bulb_state = False
        self.lock.release()
        logging.debug('Lights turned off')

    def turn_on_outlets(self):
        ''' Method to turn on outlets
        '''
        self.lock.acquire()
        for outlet in self.outlets:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{outlet}/set/state', 'ON')
            if rc != 0:
                logging.error(f'MQTT publish return code: {rc}')
        self.outlet_state = True
        self.lock.release()
        logging.debug('Outlets turned on')

    def turn_off_outlets(self):
        ''' Method to turn off outlets
        '''
        self.lock.acquire()
        for outlet in self.outlets:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{outlet}/set/state', 'OFF')
            if rc != 0:
                logging.error(f'MQTT publish return code: {rc}')
        self.outlet_state = False
        self.lock.release()
        logging.debug('Outlets turned off')

    def set_brightness(self, value):
        ''' Method to set brightness of lights
        '''
        self.brightness = value
        for bulb in self.bulbs:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{bulb}/set/brightness', self.brightness)
            if rc != 0:
                logging.error(f'MQTT publish return codes: {rc}')
        logging.info(f'Brightness set to: {self.brightness}')
