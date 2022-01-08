# home-sense

This program provides home sensor monitoring on a Raspberry Pi. This modest program currently supports the [Grove AHT20 I2C
temperature and humidity sensor](https://www.seeedstudio.com/Grove-AHT20-I2C-Industrial-grade-temperature-and-humidity-sensor-p-4497.html),
a simple sump pump float switch, and one or more Zigbee networked water leak sensors.

The code makes use of a timer with a 1 second period. Ticks are counted and used 
to schedule the sampling of sensors, storing data in a local SQLite database,
and performing various checks. E-mail alerts are triggered when sensor values cross certain
predefined thresholds (as defined in the configuration file) or a water leak is reported.

This program has been used with a Raspberry Pi 3 model B+, but should work with other models as well.

## Dependencies

This project uses Python version 3 and relies on several packages which can be installed as follows:
```
$ pip3 install configparser sqlite3 RPi.GPIO adafruit-circuitpython-ahtx0 smtplib paho-mqtt
```
This program assumes [zigbee2mqtt]() is installed and running locally in order to provide 
a bridge to any zigbee network sensors (like these [water leak sensors](https://www.zigbee2mqtt.io/devices/LS21001.html)).
Detailed setup and installation instructions for `zigbee2mqtt` (including how to bind devices)
is described in the [pi-lights](https://github.com/dschuurman/pi-lights) README project documentation.

Finally, this project assumes the presence of a local web server (such as `nginx` or `lighttpd`)
with `php` enabled to serve the `chart.php` file to display a record of data values collected.

## Setup

Place the program and the configuration file `home-sense.conf`
in the same folder. Adjust the settings in the configuration file to reflect your local settings.
In particular, you can set the thresholds at which alert e-mails will be triggered.
You will also need to specify the "friendly names" of any Zigbee water
leak sensors along with the MQTT broker address for reaching the
Zigbee network. An SMTP server needs to be specified to support e-mail alerts.

A PHP webfile is also included to visualize charts of the logged sensor data
in a convenient webpage. This should be placed in a folder that can
be read by a local webserver. The PHP file should be updated with the correct path to the database file.
Note that a webserver with PHP enabled must be present for this page to operate correctly,
and the SQLite data file needs to be readable by the web server user (typically `www-data`).

## Security considerations

Note this assumes a web server is running locally (which can increase potential security risks).
This program is intended to be run on a private home network and is provided "as is" without any warranty, 
expressed or implied, about merchantability or fitness for a particular purpose. Your mileage may vary.