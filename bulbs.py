# Part of the Pi-Home automation script for Zigbee lights, sockets, and sensors to run on a Raspberry Pi
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

# Constants
FIXED = 0
DUSK = 1
DAWN = 2

#### Bulb class definitions ####

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

        # Use a mutex for thread synchronization
        self.lock = Lock()

        # Initialize bulbs on and off times
        self.off_hour = 23
        self.off_minute = 59
        self.on_hour = 18
        self.on_minute = 00

        # Initialize bulbs to come on at dusk and turn off at dawn
        # These modes may be set to either DUSK, DAWN, or FIXED
        self.on_time_mode = DUSK
        self.off_time_mode = DAWN

        # Initialize bulbs state and timer control
        self.state = False
        self.timer = True
        self.enable_timer()

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

    def update_scheduler_queue(self):
        # Remove existing bulb entries in the scheduler queue
        self.lock.acquire()
        for event in self.scheduler.queue:
            if event.action == self.bulbs_off or event.action == self.bulbs_on:
                self.scheduler.cancel(event)   # Purge event from the queue
        self.lock.release()
        if self.timer:    # If timer is enabled, place updated bulb events in the scheduler
            if self.get_next_on_time() < self.get_next_off_time():
                self.bulbs_off()
            else:
                self.bulbs_on()
        logging.info(f'Scheduler event queue updated')

    def disable_timer(self):
        ''' Disable timer for bulbs and clear any timer events in the scheduler
        '''
        self.timer = False
        # Remove existing bulb entries in the scheduler queue
        self.update_scheduler_queue()
        logging.info(f'Timer control of bulbs DISABLED at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')

    def enable_timer(self):
        ''' Enable timer for bulbs and schedule next timer event
        '''
        self.timer = True
        # Remove existing bulb entries in the scheduler queue
        self.update_scheduler_queue()
        logging.info(f'Timer control of bulbs ENABLED at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')

    def get_next_on_time(self):
        ''' Get next bulbs on-time based on current mode
        '''
        if self.on_time_mode == FIXED:
            bulbs_on_time = datetime.now().replace(hour=self.on_hour, minute=self.on_minute, second=0)
            # If bulbs on-time has already passed for today, return on-time for tomorrow
            if bulbs_on_time < datetime.now():
                bulbs_on_time += timedelta(days=1)
        elif self.on_time_mode == DUSK:
            # set bulb on time to next dusk time
            bulbs_on_time = self.get_next_dusk_time()
        elif self.on_time_mode == DAWN:
            # turning bulbs on at dawn is unusal, but included for completeness
            bulbs_on_time = self.get_next_dawn_time()
        else:
            logging.debug(f'unrecognized bulb on-time mode: {self.on_time_mode}')
        return bulbs_on_time

    def get_next_off_time(self):
        ''' Get next bulbs off-time based on current mode
        '''
        if self.off_time_mode == FIXED:
            bulbs_off_time = datetime.now().replace(hour=self.off_hour, minute=self.off_minute, second=0)
            # If bulbs off-time has already passed for today, return off-time for tomorrow
            if bulbs_off_time < datetime.now():
                bulbs_off_time += timedelta(days=1)
        elif self.off_time_mode == DAWN:
            # set bulb to next dawn time
            bulbs_off_time = self.get_next_dawn_time()
        elif self.off_time_mode == DUSK:
            # turning bulbs off at dusk is unusal, but included for completeness
            bulbs_off_time = self.get_next_dusk_time()
        else:
            logging.debug(f'unrecognized bulb off-time mode: {self.off_time_mode}')
        return bulbs_off_time

    def get_next_dusk_time(self):
        ''' Determine next dusk time for based on city
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
        ''' Determine next dawn time based on city
        '''
        try:
            city = lookup(self.city, database())
        except KeyError:         # Log error and return 5PM by default if city not found
            logging.error(f'Unrecognized city {self.city}, using default dusk time of 5PM.')
            return datetime.today().replace(hour=17, minute=0)
        # Compute dawn time for today (corresponding to a solar depression angle of 6 degrees)
        s = sun(city.observer, tzinfo=city.timezone)
        dawn = s['dawn']
        dawn = dawn.replace(tzinfo=None)  # remove timezone to be compatible with datetime

        # If dawn time has already passed for today, return next dusk time for tomorrow
        if dawn < datetime.now():
            s = sun(city.observer, tzinfo=city.timezone, date=date.today()+timedelta(days=1))
            dawn = s['dawn']
            dawn = dawn.replace(tzinfo=None)
        return dawn

    def turn_on_bulbs(self):
        ''' Method to turn on all the bulbs
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
