# home-sense

This program provides home sensor monitoring on a Raspberry Pi using sensors connected with the
[Zigbee](https://en.wikipedia.org/wiki/Zigbee) wireless protocol. 
This code was written for a Raspberry Pi using a Zigbee USB stick, but it could be run on other 
POSIX compliant systems using a compatible Zigbee adapter.
This modest program currently supports a variety of Zigbee networked sensors 
to measure temperature, humidity, air pressure, and water leaks.

The code makes use of a timer with a 5 minute period to store data in a local SQLite database. 
E-mail alerts are triggered when sensor values cross certain predefined thresholds 
(as defined in the configuration file) or a water leak or low battery is detected.

All the code and data are stored locally on a Raspberry Pi and alerts can be sent using email.

## Dependencies

This project uses Python version 3 and relies on several packages which can be installed as follows:
```
$ pip3 install configparser sqlite3 smtplib paho-mqtt flask waitress 
```
This program assumes [zigbee2mqtt](https://www.zigbee2mqtt.io/) is installed and running locally in order to provide 
a bridge to the zigbee network sensors (like these [water leak sensors](https://www.zigbee2mqtt.io/devices/LS21001.html)
and [temperature and humidity sensors](https://www.zigbee2mqtt.io/devices/WSDCGQ12LM.html)).
Detailed setup and installation instructions for `zigbee2mqtt` (including how to bind devices)
is described in the [pi-lights](https://github.com/dschuurman/pi-lights) README project documentation.

This project uses [flask](https://flask.palletsprojects.com) to provide a local accessible webpage to display sensor values.
The webpage includes javascript code that uses the [plotly](https://plotly.com/) library to plot a chart of sensor 
values collected in the last day, month, and year.

Finally, this project requires access to an SMTP server to send e-mail alerts.
The program can make use of a local SMTP server or one can run 
[Postfix](https://www.postfix.org/BASIC_CONFIGURATION_README.html) on the localhost 
to relay mail to another SMTP server. Postfix can be setup to handle secure SASL 
authenticated communucations in order to relay mail to an external SMTP server. 
Note that some ISPs may require that you adjust your mail settings to allow for external email clients.

## Setup

Place the program and the configuration file `home-sense.conf`
in the same folder. Adjust the settings in the configuration file to reflect your local settings.
In particular, set the thresholds at which e-mail alerts will be triggered.
You will also need to specify the "friendly names" of any Zigbee sensors you are using
along with the IP Address of the MQTT broker for reaching the Zigbee network
(ideally the broker is also run on the local host).

Data is logged to an SQLite3 database file (the name and optional path are specified in `home-sense.conf`).
A webfile `chart.html` is included in a `templates` subfolder which allows visualizing the logged sensor data
in a convenient webpage. The program relies on the The [flask](https://palletsprojects.com/p/flask/) 
web framework to provide a convenient web interface. Flask’s built-in development WSGI server is 
[not designed to be particularly efficient, stable, or secure](https://flask.palletsprojects.com/en/master/server/)
so this project uses the [waitress](https://github.com/Pylons/waitress) server instead.
The web server runs on port 8080 by default (so the Zigbee2MQTT web front end should be configured 
to run on another port, such as 8081, to avoid a port conflict).
The `home-sense.conf` configuration file includes an option to easily enable or disable the web interface.
The web interface should be run on a secure local network since the web pages are open and unencrypted.


## Security considerations

Note this assumes a web server is running locally (which can increase potential security risks).
This program is intended to be run on a private home network and is provided "as is" without any warranty, 
expressed or implied, about merchantability or fitness for a particular purpose. Your mileage may vary.