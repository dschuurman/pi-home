# Home-sense program for use with Zigbee devices and a Raspberry Pi
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from threading import Thread
from flask import Flask, render_template, request
from waitress import serve
from datetime import datetime
import sqlite3
import math
import logging

# Constants
TABLE = 'SensorData'
NUMBER_OF_PLOT_POINTS = 1000

class FlaskThread(Thread):
    ''' Class definition to run flask to provide web pages to display sensor data
    '''
    def __init__(self, port, bulbs, outlets, sensors, events, database, logfile, version):
        self.port = port
        self.bulbs = bulbs
        self.outlets = outlets
        self.sensors = sensors
        self.events = events
        self.database = database
        self.logfile = logfile
        self.version = version
        Thread.__init__(self)

        # Create a flask object and initialize web pages
        self.app = Flask(__name__)
        self.app.debug = True        
        self.app.add_url_rule('/', 'index', self.index)
        self.app.add_url_rule('/bulbs', 'bulbs', self.bulbs_page, methods=['GET', 'POST'])
        self.app.add_url_rule('/outlets', 'outlets', self.outlets_page, methods=['GET', 'POST'])
        self.app.add_url_rule('/sensors', 'sensors', self.sensors_page, methods=['GET', 'POST'])
        self.app.add_url_rule('/log', 'log', self.log)
        self.app.add_url_rule('/about', 'about', self.about)

    def run(self):
        # Start the waitress WSGI server on the specified port
        serve(self.app, host='0.0.0.0', port=self.port)

    # Methods for each flask webpage route
    def index(self):
        ''' Returns index.html webpage to show system status
        '''
        # Get bulbs on and off times
        bulbs_on_time=self.bulbs.get_next_on_time().strftime("%H:%M")
        bulbs_off_time=self.bulbs.get_next_off_time().strftime("%H:%M")
        outlets_on_time=self.outlets.get_next_on_time().strftime("%H:%M")
        outlets_off_time=self.outlets.get_next_off_time().strftime("%H:%M")
        device_list = self.sensors.sensor_list + self.bulbs.bulbs_list + self.outlets.outlets_list
        
        # Create a list of scheduled timer events to display
        schedule = []
        for event in self.events.scheduler.queue:
            schedule.append(f'time={datetime.fromtimestamp(event.time).strftime("%H:%M")}, action={event.action.__name__}')

        # pass the output state to index.html to display current state on webpage
        return render_template('index.html', device_list=device_list, temperature=self.sensors.get_temperature(), humidity=self.sensors.get_humidity(), pressure=self.sensors.get_pressure(), bulbs_state=self.bulbs.state, bulbs_on_time_mode=self.bulbs.on_time_mode, bulbs_on_time=bulbs_on_time, bulbs_off_time_mode=self.bulbs.off_time_mode, bulbs_off_time=bulbs_off_time, bulbs_timer=self.bulbs.timer, outlets_state=self.outlets.state, outlets_on_time_mode=self.outlets.on_time_mode, outlets_on_time=outlets_on_time, outlets_off_time_mode=self.outlets.off_time_mode, outlets_off_time=outlets_off_time, outlets_timer=self.outlets.timer, brightness=str(self.bulbs.brightness), water_leak=self.sensors.water_leak, low_battery=self.sensors.low_battery, schedule=schedule)

    # Methods for each flask webpage route
    def bulbs_page(self):
        ''' Returns bulbs.html webpage, methods=['GET', 'POST']
        '''
        # Get bulbs on and off times
        on_time=self.bulbs.get_next_on_time().strftime("%H:%M")
        off_time=self.bulbs.get_next_off_time().strftime("%H:%M")
        timer_msg = ''

        # Process POST actions if requested
        if request.method == 'POST':
            # Get form post as a dictionary
            form_dict = request.form
            if form_dict.get('bulb_state', None) == 'on':
                # turn bulbs on
                self.bulbs.turn_on_bulbs()
                logging.info(f'Bulb(s) turned on via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('bulb_state', None) == 'off':
                # turn bulbs off
                self.bulbs.turn_off_bulbs()
                logging.info(f'Bulb(s) turned off via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('bulb_timer', None) == 'on':
                # Enable timer control of bulbs
                self.bulbs.enable_timer()
            elif form_dict.get('bulb_timer', None) == 'off':
                # Disable timer control of bulbs
                self.bulbs.disable_timer()
            elif form_dict.get('brightness', None) != None:
                self.bulbs.set_brightness(int(form_dict.get('brightness')))
            elif form_dict.get('on_time_mode', None) != None:
                if form_dict.get('on_time_mode') == 'dusk':
                    self.bulbs.on_time_mode = 'dusk'
                    logging.info('Bulbs set to come on at dusk')
                    timer_msg = 'Time update successful!'
                else:
                    self.bulbs.on_time_mode = 'fixed'
                    time = request.form['on_time']
                    if time == '':
                        logging.error('Invalid bulbs off time requested.')
                        timer_msg = 'Invalid time!'
                    else:
                        t = time.split(':')
                        self.bulbs.set_on_time(int(t[0]),int(t[1]))
                        # Update bulbs on and off times
                        timer_msg = 'Time update successful!'
                        logging.info('Bulbs set to turn on at a fixed time')
                # Update on time displayed on web page
                on_time=self.bulbs.get_next_on_time().strftime("%H:%M")

            elif form_dict.get('off_time_mode', None) != None:
                if form_dict.get('off_time_mode') == 'dawn':
                    self.bulbs.off_time_mode = 'dawn'
                    logging.info('Bulbs set to turn off at dawn')
                    timer_msg = 'Time update successful!'
                else:
                    self.bulbs.off_time_mode = 'fixed'
                    time = request.form['off_time']
                    if time == '':
                        logging.error('Invalid bulbs off time requested.')
                        timer_msg = 'Invalid time!'
                    else:
                        t = time.split(':')
                        self.bulbs.set_off_time(int(t[0]),int(t[1]))
                        # Update bulbs on and off times
                        timer_msg = 'Time update successful!'
                        logging.info('Bulbs off updated to a fixed time')
                # update off time displayed on web page
                off_time=self.bulbs.get_next_off_time().strftime("%H:%M")

            # Return success (201) and stay on the same page
            return render_template('bulbs.html', timer_msg=timer_msg, on_time_mode=self.bulbs.on_time_mode, off_time_mode=self.bulbs.off_time_mode, on_time=on_time, off_time=off_time, bulbs=str(self.bulbs), state=self.bulbs.state, timer=self.bulbs.timer, brightness=str(self.bulbs.brightness)), 200

        elif request.method == 'GET':
            # pass the output state to bulbs.html to display current state on webpage
            return render_template('bulbs.html', timer_msg=timer_msg, on_time_mode=self.bulbs.on_time_mode, off_time_mode=self.bulbs.off_time_mode, on_time=on_time, off_time=off_time, bulbs=str(self.bulbs), state=self.bulbs.state, timer=self.bulbs.timer, brightness=str(self.bulbs.brightness))

    def outlets_page(self):
        ''' Returns outlets.html webpage, methods=['GET', 'POST']
        '''
        # Get outlets on and off times
        on_time=self.outlets.get_next_on_time().strftime("%H:%M")
        off_time=self.outlets.get_next_off_time().strftime("%H:%M")
        timer_msg = ''

        # Process POST actions if requested
        if request.method == 'POST':
            # Get form post as a dictionary
            form_dict = request.form
            if form_dict.get('outlet_state', None) == 'on':
                # Turn outlet on
                self.outlets.turn_on_outlets()
                logging.info(f'Outlet(s) turned on via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('outlet_state', None) == 'off':
                # Turn outlet off
                self.outlets.turn_off_outlets()
                logging.info(f'Outlet(s) turned off via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('outlet_timer', None) == 'on':
                # Enable timer control of outlets
                self.outlets.enable_timer()
            elif form_dict.get('outlet_timer', None) == 'off':
                # Disable timer control of outlets
                self.outlets.disable_timer()
            elif form_dict.get('on_time_mode', None) != None:
                if form_dict.get('on_time_mode') == 'dusk':
                    self.outlets.on_time_mode = 'dusk'
                    logging.info('Outlets set to come on at dusk')
                    timer_msg = 'Outlets time update successful!'
                else:
                    self.outlets.on_time_mode = 'fixed'
                    time = request.form['on_time']
                    if time == '':
                        logging.error('Invalid outlets off time requested.')
                        timer_msg = 'Invalid time!'
                    else:
                        t = time.split(':')
                        self.outlets.set_on_time(int(t[0]),int(t[1]))
                        # Update bulbs on and off times
                        timer_msg = 'Outlets time update successful!'
                        logging.info(f'Outlets set to turn on at a fixed time at {time}')
                # Update on time displayed on web page
                on_time=self.outlets.get_next_on_time().strftime("%H:%M")

            elif form_dict.get('off_time_mode', None) != None:
                if form_dict.get('off_time_mode') == 'dawn':
                    self.outlets.off_time_mode = 'dawn'
                    logging.info('Outlets set to turn off at dawn')
                    timer_msg = 'Outlets time update successful!'
                else:
                    self.outlets.off_time_mode = 'fixed'
                    time = request.form['off_time']
                    if time == '':
                        logging.error('Invalid outlets off time requested.')
                        timer_msg = 'Invalid time!'
                    else:
                        t = time.split(':')
                        self.outlets.set_off_time(int(t[0]),int(t[1]))
                        # Update outlets on and off times
                        timer_msg = 'Outlets time update successful!'
                        logging.info(f'Outlets off updated to a fixed time at {time}')
                # update off time displayed on web page
                off_time=self.outlets.get_next_off_time().strftime("%H:%M")

            # Return success (201) and stay on the same page
            return render_template('outlets.html', timer_msg=timer_msg, on_time_mode=self.outlets.on_time_mode, off_time_mode=self.outlets.off_time_mode, on_time=on_time, off_time=off_time, outlets=str(self.outlets), state=self.outlets.state, timer=self.outlets.timer), 200

        elif request.method == 'GET':
            # pass the output state to display current state on webpage
            return render_template('outlets.html', timer_msg=timer_msg, on_time_mode=self.outlets.on_time_mode, off_time_mode=self.outlets.off_time_mode, on_time=on_time, off_time=off_time, outlets=str(self.outlets), state=self.outlets.state, timer=self.outlets.timer)

    def sensors_page(self):
        ''' Returns chart.html webpage
        '''

        # TO-DO: Show a default page if no data is in the database yet.

        logging.info(f'Web request to display charts of sensor data at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')

        self.db = sqlite3.connect(self.database)
        self.cursor = self.db.cursor()
        day_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-1 day')").fetchall()

        count = self.cursor.execute(f"SELECT COUNT(*) FROM {TABLE} where datetime > datetime('now','localtime','-30 day')").fetchone()[0]
        skip = math.ceil(count/NUMBER_OF_PLOT_POINTS)  # Number of rows to skip over for each point to ensure number of plot points stays reasonable
        month_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-30 day') AND ROWID % {skip} = 0").fetchall()

        count = self.cursor.execute(f"SELECT COUNT(*) FROM {TABLE} where datetime > datetime('now','localtime','-365 day')").fetchone()[0]
        skip = math.ceil(count/NUMBER_OF_PLOT_POINTS)  # Number of rows to skip over for each point to ensure number of plot points stays reasonable
        year_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-365 day') AND ROWID % {skip} = 0").fetchall()

        self.db.close()

        email = f'{self.events.mail.to_address} sent via {self.events.mail.server}'

        if request.method == 'POST':
            form_dict = request.form
            if form_dict.get('test_email', None) == 'test':
                self.events.mail.send('home-sense test email','This is a test email sent from your home-sense server.')
                logging.info(f'Test email sent {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            return render_template('sensors.html', sensors=str(self.sensors), water_leak=self.sensors.water_leak, low_battery=self.sensors.low_battery, day_data=day_data, month_data=month_data, year_data=year_data, email=email), 200
        elif request.method == 'GET':
            return render_template('sensors.html', sensors=str(self.sensors), water_leak=self.sensors.water_leak, low_battery=self.sensors.low_battery, day_data=day_data, month_data=month_data, year_data=year_data, email=email)

    def log(self):
        ''' Returns webpage /log
        '''
        f = open(self.logfile, 'r')
        log = f.read()
        f.close()
        log = log.replace('\n', '<br>\n')
        return render_template('log.html', log=log)

    def about(self):
        ''' Returns webpage /about
        '''
        return render_template('about.html', version=self.version)