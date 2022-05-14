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

#### Class definitions ####

class Bulbs:
    ''' Bulbs class used to schedule and control smart bulbs
    '''
    def __init__(self, bulbs_list, brightness, scheduler, client, city):
        ''' Constructor 
        '''
        # Store bulbs and brightness settings
        self.bulbs_list = bulbs_list
        self.scheduler = scheduler
        self.client = client
        self.city = city

        self.set_brightness(brightness)
        logging.info(f'Devices: {bulbs_list}')

        # Set default bulbs on and off times
        self.off_hour = 23
        self.off_minute = 59
        self.on_hour = 18
        self.on_minute = 00

        # Initialize timer control of bulbs to be enabled (normally used for porch bulbs)
        self.timer = True

        # Use a mutex for thread synchronization
        self.lock = Lock()

        # Initialize bulbs to come on at dusk and turn off at a fixed time
        # modes are set to either "dusk" or "fixed"
        self.on_time_mode = 'dusk'
        self.off_time_mode = 'fixed'
        on_time = self.get_next_dusk_time()
        today = datetime.now().date()
        on_time = on_time.replace(year=today.year, month=today.month, day=today.day)   

        # Initialize bulbs and schedule events
        self.state = False

        # If current time is between bulbs ON and OFF then set bulbs ON and schedule event for OFF time
        if on_time <= datetime.now() < self.get_next_off_time():
            self.bulbs_on()
        # Otherwise turn bulbs OFF and schedule event to turn bulbs ON at next dusk time
        else:
            self.bulbs_off()

    def bulbs_on(self):
        ''' turn bulbs on and schedule next event to turn bulbs off
        '''
        logging.info(f'*** Turning Bulbs ON at {datetime.now().strftime("%m/%d/%Y %H:%M:%S")} ***')
        self.turn_on_bulbs()

        # set next bulbs off time
        logging.info(f'Next event = Bulbs OFF at: {self.get_next_off_time().strftime("%m/%d/%Y, %H:%M:%S")}')
        seconds = round((self.get_next_off_time() - datetime.now()).total_seconds())
        self.scheduler.enter(seconds, 1, self.bulbs_off)

    def bulbs_off(self):
        ''' turn bulbs off and schedule next event to turn bulbs on
        '''
        logging.info(f'*** Turning Bulbs OFF at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")} ***')
        self.turn_off_bulbs()

        # set next bulbs on time
        logging.info(f'Next event = Bulbs ON at: {self.get_next_on_time().strftime("%m/%d/%Y, %H:%M:%S")}')
        seconds = round((self.get_next_on_time() - datetime.now()).total_seconds())
        self.scheduler.enter(seconds, 1, self.bulbs_on)

    def set_on_time(self, hour, minute):
        ''' Set Bulbs on time
        '''
        # Update new bulbs on time
        self.on_hour = hour
        self.on_minute = minute
        logging.info(f'Bulbs ON time changed to: {self.on_hour}:{self.on_minute:02}')

        # Search scheduler queue to remove current light event before inserting new one
        for event in self.scheduler.queue:
            if event.action == self.bulbs_off or event.action == self.bulbs_on:
                self.scheduler.cancel(event)   # Purge old event from the queue
        # If bulbs should now be on: turn them on (and add next event to the queue)
        if datetime.now() < self.get_next_off_time() < self.get_next_dusk_time():
            self.bulbs_on()
        else:   # Otherwise turn bulbs off (and add the next event to the queue)
            self.bulbs_off()

    def set_off_time(self, hour, minute):
        ''' Set bulbs out time
        '''
        # Update new bulbs out time
        self.off_hour = hour
        self.off_minute = minute
        logging.info(f'Bulbs out time changed to: {self.off_hour}:{self.off_minute:02}')

        # Search scheduler queue to remove current light event before inserting new one
        for event in self.scheduler.queue:
            if event.action == self.bulbs_off or event.action == self.bulbs_on:
                self.scheduler.cancel(event)   # Purge old event from the queue
        # If bulbs should now be on: turn them on (and add next event to the queue)
        if datetime.now() < self.get_next_off_time() < self.get_next_dusk_time():
            self.bulbs_on()
        else:   # Otherwise turn bulbs off (and add the next event to the queue)
            self.bulbs_off()

    def get_next_on_time(self):
        ''' Get next bulbs on time
        '''
        if self.on_time_mode == 'fixed':
            bulbs_on_time = datetime.now().replace(hour=self.on_hour, minute=self.on_minute, second=0)
            # If bulbs on time has already passed for today, return bulbs on time for tomorrow
            if bulbs_on_time < datetime.now():
                bulbs_on_time += timedelta(days=1)
        else:
            # if bulbs on time is not fixed, then set to next dusk time
            bulbs_on_time = self.get_next_dusk_time()
        return bulbs_on_time

    def get_next_off_time(self):
        ''' Get next bulbs out time
        '''
        if self.off_time_mode == 'fixed':
            bulbs_off_time = datetime.now().replace(hour=self.off_hour, minute=self.off_minute, second=0)
            # If bulbs out time has already passed for today, return bulbs out time for tomorrow
            if bulbs_off_time < datetime.now():
                bulbs_off_time += timedelta(days=1)
        else:
            # if bulbs out time is not fixed, then set to next dawn time
            bulbs_off_time = self.get_next_dawn_time()
        return bulbs_off_time

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
        for bulb in self.bulbs_list:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{bulb}/set/state', 'ON')
            if rc != 0:
                logging.error(f'MQTT publish return codes: {rc}')
        self.state = True
        self.lock.release()
        logging.debug('Bulbs turned on')

    def turn_off_bulbs(self):
        ''' Method to turn off all bulbs
        '''
        self.lock.acquire()
        for bulb in self.bulbs_list:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{bulb}/set/state', 'OFF')
            if rc != 0:
                logging.error(f'MQTT publish return code: {rc}')       
        self.state = False
        self.lock.release()
        logging.debug('Bulbs turned off')

    def set_brightness(self, value):
        ''' Method to set brightness of smart bulbs
        '''
        self.brightness = value
        for bulb in self.bulbs_list:
            (rc, msg_id) = self.client.publish(f'zigbee2mqtt/{bulb}/set/brightness', self.brightness)
            if rc != 0:
                logging.error(f'MQTT publish return codes: {rc}')
        logging.info(f'Brightness set to: {self.brightness}')

    def __str__(self):
        bulb_str = self.bulbs_list[0]
        for i in range(1,len(self.bulbs_list)):
            bulb_str += f', {self.bulbs_list[i]}'
        return bulb_str