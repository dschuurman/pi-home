# Home Automation script for Zigbee lights, sockets, and sensors to run on Raspberry Pi
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import paho.mqtt.client as mqtt
import logging
from datetime import date, datetime, timezone, timedelta
from astral.sun import sun
from astral.geocoder import lookup, database
from threading import Thread, Lock
import sched, time

#### Class definition ####

class Outlets:
    ''' Outlets class used to schedule and control smart outlets
    '''
    def __init__(self, outlets_list, scheduler, client, city):
        ''' Constructor 
        '''
        self.outlets_list = outlets_list
        logging.info(f'Outlets: {outlets_list}')

        self.scheduler = scheduler
        self.client = client
        self.city = city

        # Set outlets times to fixed time by default
        self.on_time_mode = 'fixed'    # mode is either set to "dusk" or "fixed"
        self.off_time_mode = 'fixed'    # mode is either set to "dawn" or "fixed"

        # Set fixed outlets on and off times
        self.off_hour = 23
        self.off_minute = 00
        self.on_hour = 18
        self.on_minute = 00

        # Initialize timer control of outlets to be disabled
        self.timer = False

        # Use a mutex for thread synchronization
        self.lock = Lock()

        # Initialize outlets state
        self.state = False
        self.turn_off_outlets()

    def outlets_on(self):
        ''' turn outlets on and schedule next event to turn outlets off
        '''
        if self.timer:
            logging.info(f'*** Turning outlets ON at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")} ***')
            self.turn_on_outlets()

        # set next outlets off time
        logging.info(f'Next event = Outlets OFF at: {self.get_next_off_time().strftime("%m/%d/%Y, %H:%M:%S")}')
        seconds = round((self.get_next_off_time() - datetime.now()).total_seconds())
        self.scheduler.enter(seconds, 1, self.outlets_off)

    def outlets_off(self):
        ''' turn outlets off and schedule next event to turn outlets on
        '''
        if self.timer:
            logging.info(f'*** Turning outlets OFF at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")} ***')
            self.turn_off_outlets()       

        # set next outlets on time
        logging.info(f'Next event = outlets ON at: {self.get_next_on_time().strftime("%m/%d/%Y, %H:%M:%S")}')
        seconds = round((self.get_next_on_time() - datetime.now()).total_seconds())
        self.scheduler.enter(seconds, 1, self.outlets_on)

    def set_on_time(self, hour, minute):
        ''' Set outlets on time
        '''
        # Update new outlets on time
        self.on_hour = hour
        self.on_minute = minute
        logging.info(f'Outlets ON time set to: {self.on_hour}:{self.on_minute:02}')

        # Search scheduler queue to remove current light event before inserting new one
        for event in self.scheduler.queue:
            if event.action == self.outlets_off or event.action == self.outlets_on:
                self.scheduler.cancel(event)   # Purge old event from the queue
        # If outlets should now be on: turn them on (and add next event to the queue)
        if datetime.now() < self.get_next_off_time() < self.get_next_dusk_time():
            self.outlets_on()
        else:   # Otherwise turn outlets off (and add the next event to the queue)
            self.outlets_off()

    def set_off_time(self, hour, minute):
        ''' Set outlets off time
        '''
        # Update new outlets out time
        self.off_hour = hour
        self.off_minute = minute
        logging.info(f'Outlets out time set to: {self.off_hour}:{self.off_minute:02}')

        # Search scheduler queue to remove current light event before inserting new one
        for event in self.scheduler.queue:
            if event.action == self.outlets_off or event.action == self.outlets_on:
                self.scheduler.cancel(event)   # Purge old event from the queue
        # If outlets should now be on: turn them on (and add next event to the queue)
        if datetime.now() < self.get_next_off_time() < self.get_next_dusk_time():
            self.outlets_on()
        else:   # Otherwise turn outlets off (and add the next event to the queue)
            self.outlets_off()

    def get_next_on_time(self):
        ''' Get next outlets on time
        '''
        if self.on_time_mode == 'fixed':
            outlets_on_time = datetime.now().replace(hour=self.on_hour, minute=self.on_minute, second=0)
            # If outlets on time has already passed for today, return outlets on time for tomorrow
            if outlets_on_time < datetime.now():
                outlets_on_time += timedelta(days=1)
        else:
            # if outlets on time is not fixed, then set to next dusk time
            outlets_on_time = self.get_next_dusk_time()
        return outlets_on_time

    def get_next_off_time(self):
        ''' Get next outlets out time
        '''
        if self.off_time_mode == 'fixed':
            outlets_off_time = datetime.now().replace(hour=self.off_hour, minute=self.off_minute, second=0)
            # If outlets out time has already passed for today, return outlets out time for tomorrow
            if outlets_off_time < datetime.now():
                outlets_off_time += timedelta(days=1)
        else:
            # if outlets out time is not fixed, then set to next dawn time
            outlets_off_time = self.get_next_dawn_time()
        return outlets_off_time

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

    def turn_on_outlets(self):
        ''' Method to turn on outlets
        '''
        self.lock.acquire()
        for outlet in self.outlets_list:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{outlet}/set/state', 'ON')
            if rc != 0:
                logging.error(f'MQTT publish return code: {rc}')
        self.state = True
        self.lock.release()
        logging.debug('Outlets turned on')

    def turn_off_outlets(self):
        ''' Method to turn off outlets
        '''
        self.lock.acquire()
        for outlet in self.outlets_list:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{outlet}/set/state', 'OFF')
            if rc != 0:
                logging.error(f'MQTT publish return code: {rc}')
        self.state = False
        self.lock.release()
        logging.debug('Outlets turned off')

    def __str__(self):
        outlet_str = self.outlets_list[0]
        for i in range(1,len(self.outlets_list)):
            outlet_str += f', {self.outlets_list[i]}'
        return outlet_str
