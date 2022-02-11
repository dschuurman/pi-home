# Home-sense program for use with Zigbee devices and a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from threading import Thread
from flask import Flask, render_template, request
from waitress import serve
import sqlite3
import math

# Constants
TABLE = 'SensorData'
NUMBER_OF_PLOT_POINTS = 1000

class FlaskThread(Thread):
    ''' Class definition to run flask to provide web pages to display sensor data
    '''
    def __init__(self, port, database):
        self.port = port
        self.database = database
        Thread.__init__(self)

        # Create a flask object and initialize web pages
        self.app = Flask(__name__)
        self.app.debug = True
        self.app.add_url_rule('/', 'chart', self.chart)

    def run(self):
        # Start the waitress WSGI server on the specified port
        serve(self.app, host='0.0.0.0', port=self.port)

    # Methods for each flask webpage route
    def chart(self):
        ''' Returns chart.html webpage
        '''
        self.db = sqlite3.connect(self.database)
        self.cursor = self.db.cursor()
        day_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-1 day')").fetchall()

        count = self.cursor.execute(f"SELECT COUNT(*) FROM {TABLE} where datetime > datetime('now','localtime','-30 day')").fetchone()[0]
        skip = math.ceil(count/NUMBER_OF_PLOT_POINTS)  # Number of rows to skip over for each point to ensure number of plot points stays reasonable
        month_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-30 day') AND ROWID % {skip} = 0").fetchall()

        count = self.cursor.execute(f"SELECT COUNT(*) FROM {TABLE} where datetime > datetime('now','localtime','-365 day')").fetchone()[0]
        skip = math.ceil(count/NUMBER_OF_PLOT_POINTS)  # Number of rows to skip over for each point to ensure number of plot points stays reasonable
        year_data = self.cursor.execute(f"SELECT datetime,temperature,humidity,pressure FROM {TABLE} where datetime > datetime('now','localtime','-365 day') AND ROWID % {skip} = 0").fetchall()
        return render_template('chart.html', day_data=day_data, month_data=month_data, year_data=year_data)