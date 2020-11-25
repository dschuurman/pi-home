# pi-home-monitor

This program provides home sensor monitoring on a Raspberry Pi. This modest program currently supports a 
[temperature and humidity sensor](https://www.seeedstudio.com/Grove-AHT20-I2C-Industrial-grade-temperature-and-humidity-sensor-p-4497.html)
and a simple sump pump float switch.

The code makes use of a timer with a 1 second period. Ticks are counted and used 
to schedule the sampling of sensors, storing data in a local SQLite database,
and performing various checks. E-mail alerts are triggered when sensor values cross certain
predefined thresholds (as defined in the configuration file).

This program has been used with a Raspberry Pi 3 model B+, but should work with other models as well.

This program is provided "as is" without any warranty, expressed or implied, about merchantability or fitness for a particular purpose.
Your mileage may vary.

## Dependencies

This project uses Python version 3 and relies on several packages which can be installed as follows:
```
$ pip3 install configparser sqlite3 RPi.GPIO adafruit-circuitpython-ahtx0 smtplib
```
## Setup

Place the program and the configuration file `home-monitor.conf`
in the same folder. Adjust the settings in the configuration file to reflect your local settings.
In particular, you can set the thresholds at which alert e-mails will be triggered.
Note that to support alert e-mails, this program assumes access to an SMTP server for sending messages.

A PHP webfile is also included to visualize charts of the logged sensor data
in a convenient webpage. This should be placed in a folder that can
be read by a webserver. The PHP file should be updated with the correct path to the database file.
Note that a webserver with PHP enabled must be present for this page to operate correctly,
and the SQLite data file needs to be readable by the web server user (www-data).

## Security considerations

Note that running a webserver server will increase potential security risks and vulnerabilities.
