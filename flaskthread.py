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
    def __init__(self, port, lights, sensors, database, logfile, version):
        self.port = port
        self.lights = lights
        self.sensors = sensors
        self.database = database
        self.logfile = logfile
        self.version = version
        Thread.__init__(self)

        # Create a flask object and initialize web pages
        self.app = Flask(__name__)
        self.app.debug = True        
        self.app.add_url_rule('/', 'index', self.index)
        self.app.add_url_rule('/bulbs', 'bulbs', self.bulbs, methods=['GET', 'POST'])
        self.app.add_url_rule('/outlets', 'outlets', self.outlets, methods=['GET', 'POST'])
        self.app.add_url_rule('/sensors', 'sensors', self.sensors_page)
        self.app.add_url_rule('/log', 'log', self.log)
        self.app.add_url_rule('/about', 'about', self.about)

    def run(self):
        # Start the waitress WSGI server on the specified port
        serve(self.app, host='0.0.0.0', port=self.port)

    # Methods for each flask webpage route
    def index(self):
        ''' Returns index.html webpage to show system status
        '''
        # Get lights on and off times
        on_time=self.lights.get_next_dusk_time().strftime("%H:%M")
        off_time=self.lights.get_next_lights_out_time().strftime("%H:%M")
        device_list = self.sensors.sensor_list + self.lights.bulbs + self.lights.outlets

        # pass the output state to index.html to display current state on webpage
        return render_template('index.html', device_list=device_list, temperature=self.sensors.get_temperature(), humidity=self.sensors.get_humidity(), pressure=self.sensors.get_pressure(), on_time_mode=self.lights.on_time_mode, on_time=on_time, off_time_mode=self.lights.off_time_mode, off_time=off_time, bulb_state=self.lights.bulb_state, bulb_timer=self.lights.bulb_timer, outlet_state=self.lights.outlet_state, outlet_timer=self.lights.outlet_timer, brightness=str(self.lights.brightness), water_leak=self.sensors.water_leak, low_battery=self.sensors.low_battery)

    # Methods for each flask webpage route
    def bulbs(self):
        ''' Returns bulbs.html webpage, methods=['GET', 'POST']
        '''
        # Get lights on and off times
        on_time=self.lights.get_next_lights_on_time().strftime("%H:%M")
        off_time=self.lights.get_next_lights_out_time().strftime("%H:%M")
        timer_msg = ''

        # Process POST actions if requested
        if request.method == 'POST':
            # Get form post as a dictionary
            form_dict = request.form
            if form_dict.get('bulb_state', None) == 'on':
                # turn bulbs on
                self.lights.turn_on_bulbs()
                logging.info(f'Bulb(s) turned on via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('bulb_state', None) == 'off':
                # turn bulbs off
                self.lights.turn_off_bulbs()
                logging.info(f'Bulb(s) turned off via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('bulb_timer', None) == 'on':
                # Enable timer control of lights
                self.lights.bulb_timer = True
                logging.info(f'Timer control of bulbs ENABLED at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('bulb_timer', None) == 'off':
                # Disable timer control of lights
                self.lights.bulb_timer = False
                logging.info(f'Timer control of bulbs DISABLED at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('brightness', None) != None:
                self.lights.set_brightness(int(form_dict.get('brightness')))

            elif form_dict.get('on_time_mode', None) != None:
                if form_dict.get('on_time_mode') == 'dusk':
                    self.lights.on_time_mode = 'dusk'
                    logging.info('Lights set to come on at dusk')
                else:
                    self.lights.on_time_mode = 'fixed'
                    time = request.form['on_time']
                    if time == '':
                        logging.error('Invalid lights out time requested.')
                        timer_msg = 'Invalid time!'
                    else:
                        t = time.split(':')
                        self.lights.set_lights_on_time(int(t[0]),int(t[1]))
                        # Update lights on and off times
                        timer_msg = 'Time update successful!'
                        logging.info('Lights set to turn on at a fixed time')
                # Update on time displayed on web page
                on_time=self.lights.get_next_lights_on_time().strftime("%H:%M")

            elif form_dict.get('off_time_mode', None) != None:
                if form_dict.get('off_time_mode') == 'dawn':
                    self.lights.off_time_mode = 'dawn'
                    logging.info('Lights set to turn off at dawn')
                else:
                    self.lights.off_time_mode = 'fixed'
                    time = request.form['off_time']
                    if time == '':
                        logging.error('Invalid lights out time requested.')
                        timer_msg = 'Invalid time!'
                    else:
                        t = time.split(':')
                        self.lights.set_lights_out_time(int(t[0]),int(t[1]))
                        # Update lights on and off times
                        timer_msg = 'Time update successful!'
                        logging.info('Lights off updated to a fixed time')
                # update off time displayed on web page
                off_time=self.lights.get_next_lights_out_time().strftime("%H:%M")

            # Return success (201) and stay on the same page
            return render_template('bulbs.html', timer_msg=timer_msg, on_time_mode=self.lights.on_time_mode, off_time_mode=self.lights.off_time_mode, on_time=on_time, off_time=off_time, lights=self.lights.bulbs, outlets=self.lights.outlets, bulb_state=self.lights.bulb_state, bulb_timer=self.lights.bulb_timer, outlet_state=self.lights.outlet_state, outlet_timer=self.lights.outlet_timer, brightness=str(self.lights.brightness)), 200

        elif request.method == 'GET':
            # pass the output state to bulbs.html to display current state on webpage
            return render_template('bulbs.html', timer_msg=timer_msg, on_time_mode=self.lights.on_time_mode, off_time_mode=self.lights.off_time_mode, on_time=on_time, off_time=off_time, lights=self.lights.bulbs, outlets=self.lights.outlets, bulb_state=self.lights.bulb_state, bulb_timer=self.lights.bulb_timer, outlet_state=self.lights.outlet_state, outlet_timer=self.lights.outlet_timer, brightness=str(self.lights.brightness))

    def outlets(self):
        ''' Returns outlets.html webpage, methods=['GET', 'POST']
        '''
        # Get lights on and off times
        on_time=self.lights.get_next_dusk_time().strftime("%H:%M")
        off_time=self.lights.get_next_lights_out_time().strftime("%H:%M")
        timer_msg = ''

        # Process POST actions if requested
        if request.method == 'POST':
            # Get form post as a dictionary
            form_dict = request.form
            if form_dict.get('outlet_state', None) == 'on':
                # Turn outlet on
                self.lights.turn_on_outlets()
                logging.info(f'Outlet(s) turned on via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('outlet_state', None) == 'off':
                # Turn outlet off
                self.lights.turn_off_outlets()
                logging.info(f'Outlet(s) turned off via web interface at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('outlet_timer', None) == 'on':
                # Enable timer control of outlet
                self.lights.outlet_timer = True
                logging.info(f'Timer control of outlet ENABLED at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('outlet_timer', None) == 'off':
                # Disable timer control of outlet
                self.lights.outlet_timer = False
                logging.info(f'Timer control of outlet DISABLED at {datetime.now().strftime("%m/%d/%Y, %H:%M:%S")}')
            elif form_dict.get('off_time', None) != None:
                time = request.form['off_time']
                if time == '':
                    logging.error('Invalid lights out time requested.')
                    timer_msg = 'Invalid time!'
                else:
                    t = time.split(':')
                    self.lights.set_lights_out_time(int(t[0]),int(t[1]))
                    # Update lights on and off times
                    on_time=self.lights.get_next_dusk_time().strftime("%H:%M")
                    off_time=self.lights.get_next_lights_out_time().strftime("%H:%M")
                    timer_msg = 'Time update successful!'

            # Return success (201) and stay on the same page
            return render_template('outlets.html', timer_msg=timer_msg, on_time_mode=self.lights.on_time_mode, off_time_mode=self.lights.off_time_mode, on_time=on_time, off_time=off_time, outlets=self.lights.outlets, outlet_state=self.lights.outlet_state, outlet_timer=self.lights.outlet_timer), 200

        elif request.method == 'GET':
            # pass the output state to display current state on webpage
            #return render_template('outlets.html', on_time=on_time, on_time_mode=self.lights.on_time_mode, off_time_mode=self.lights.off_time_mode, off_time=off_time, outlets=self.lights.outlets, outlet_state=self.lights.outlet_state, outlet_timer=self.lights.outlet_timer)
            return render_template('outlets.html', timer_msg=timer_msg, on_time_mode=self.lights.on_time_mode, off_time_mode=self.lights.off_time_mode, on_time=on_time, off_time=off_time, outlets=self.lights.outlets, outlet_state=self.lights.outlet_state, outlet_timer=self.lights.outlet_timer)

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
        return render_template('sensors.html', sensor_list=self.sensors.sensor_list, water_leak=self.sensors.water_leak, low_battery=self.sensors.low_battery, day_data=day_data, month_data=month_data, year_data=year_data)

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