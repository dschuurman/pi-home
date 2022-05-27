# home-sense

Home-sense is a home automation program using smart bulbs, smart outlets,
and a variety of sensors connected using the [Zigbee](https://en.wikipedia.org/wiki/Zigbee) wireless protocol.
This code was written for a Raspberry Pi using a Zigbee USB stick, but it could be run on other 
platforms using a compatible Zigbee adapter. This modest program currently supports a variety of Zigbee 
networked sensors to sense temperature, humidity, air pressure, and water leaks.
The software also controls smart bulbs and smart outlets to turn them on at dusk 
(where dusk is determined daily by your location) and turn them off at a preset time.
The motivation for this feature was to illuminate porch lights in the evening
while ensuring they are not needlessly left on during the day. 
Furthermore, a feature to control one or more smart outlets provides the functionality 
of a traditional light timer to control indoor lights while away on vacation.

A basic web interface running on the Raspberry Pi provides a means for configuration and manually controlling the
lights and outlets and to view sensor data. One can also view plots of historical sensor data 
which is stored in a local SQLite database. 
Furthermore, e-mail alerts can be triggered when sensor values cross certain predefined thresholds 
(as defined in the configuration file) or a water leak or low battery is detected.
Note that all data and configuration settings are stored locally on the Raspberry Pi.

# Software Structure
The program parses a configuration file at start-up to set initial settings.
Separate classes are used for each category of supported Zigbee devices, including smart bulbs, 
smart outlets, and sensors. These classes provide methods for controlling and reading the state of these devices.
The software also makes use of two threads: a main thread runs the control software and another
thread runs a flask web service for viewing the current state of the system and adjusting the configuration.
A timer is used take periodic sensor samples and to schedule on and off times for the smart bulbs and outlets.
Timer events are implemented using a scheduler which stores events in a priority queue. Sensor samples are stored
in a local SQLite database and plots of historical values are available in a webpage which uses a javascript plotting library.
When sensor readings (such as temperature) exceed pre-defined thresholds or when alarms are detected 
(eg. low battery and water sensor alarms) an e-mail message can be forwarded to an SMTP server.

# Installation
This project was developed on a Raspberry Pi running 
[Raspberry Pi OS Lite](https://www.raspberrypi.org/software/operating-systems/)
and written in Python version 3. The code relies heavily on 
[Zigbee2MQTT](https://www.zigbee2mqtt.io/)
to bridge a network of Zigbee devices to MQTT (a common IoT networking protocol). 
Zigbee2MQTT supports various [Zigbee USB adapters](https://www.zigbee2mqtt.io/guide/adapters/) 
along with [numerous Zigbee devices](https://www.zigbee2mqtt.io/supported-devices/).

## Install Mosquitto
The first step is to install `mosquitto` which provides an open source MQTT broker.
This can be installed from the command-line as follows:
```
sudo apt install -y mosquitto mosquitto-clients
```
Since we will be connecting to the MQTT broker locally, we can edit the mosquitto 
congifuration file to explicitly listen *only* on the local loopback interface.
This can be done by adding the following lines in `/etc/mosquitto/conf.d/local.conf`:
```
listener 1883 127.0.0.1
allow_anonymous true
```
Next, enable the mosquitto service as follows:
```
sudo systemctl enable mosquitto.service
```
Ensure the `mosquitto` service is now running by typing:
```
sudo service mosquitto status
```

## Install Zigbee2MQTT
The next step is to install [Zigbee2MQTT](https://www.zigbee2mqtt.io/) on the Raspberry Pi. 
First, there are several dependencies that need to be installed from the command-line as follows:
```
$ sudo apt-get install -y nodejs npm git make g++ gcc
```
Once the depencies are installed, Zigbee2MQTT can be installed from github by typing the 
following commands:
```
cd $HOME
git clone https://github.com/Koenkk/zigbee2mqtt.git
sudo mv zigbee2mqtt /opt/zigbee2mqtt
cd /opt/zigbee2mqtt
npm ci
```
Zigbee2MQTT requires a [YAML](https://en.wikipedia.org/wiki/YAML) conifiguration file which 
is located at `/opt/zigbee2mqtt/data/configuration.yaml`. 
Edit the configuration file so that it inlucdes the following settings:
```
homeassistant: false
permit_join: true

# MQTT settings
mqtt:
  base_topic: zigbee2mqtt
  server: 'mqtt://localhost'

# Location of Zigbee USB adapter
serial:
  port: /dev/ttyACM0

# use a custom network key
advanced:
    network_key: GENERATE

# Start web frontend
frontend:
  port: 8080

# Enable over-the-air (OTA) updates for devices
ota:
    update_check_interval: 1440
    disable_automatic_update_check: false

```
Note that this configuration is for a Zigbee USB adapter which appears as `/dev/ttyACM0`. 
You can use the `dmesg` command to find the device file associated with
your particular Zigbee USB adapter and then update the configuration file accordingly.
Rather than hard-coding a unique network key, the `network_key` setting used above generates 
a new random key when Zigbee2MQTT is first run.

> ***Security Notes***
>
> It's recommended to disable `permit_join` after all the Zigbee devices
have been paired with your Zigbee adapter to prevent further devices
from attempting to join and possibly exposing the network key.
> It is recommended to enable over-the-air (OTA) updates for all devices to keep then up-to-date.
> The `frontend` setting provides a nifty web frontend that can be used
> for binding devices, debugging, and showing a map of the Zigbee network,
> but it also exposes device information on your local network.

Once the setup and configuration are complete, ensure the Zigbee USB adapter
is inserted in the Raspberry Pi and start Zigbee2MQTT as follows:
```
cd /opt/zigbee2mqtt
npm start
```
This will launch `zigbee2mqtt` from the command-line. Once the
it builds and launches successfully, you can exit the program by hitting ctrl-c.
To launch automaticlaly on boot under Linux, 
[setup Zigbee2MQTT to run using systemctl](https://www.zigbee2mqtt.io/guide/installation/01_linux.html#starting-zigbee2mqtt).
For more detailed informatoin about installing Zigbee2MQTT, refer to the official
[Zigbee2MQTT installation instructions](https://www.zigbee2mqtt.io/guide/installation/01_linux.html#installing).

## Setup a Zigbee Network of Devices
Next, we need to establish a network of Zigbee devices by
pairing each new device with the Zigbee hub on the Raspberry Pi.

### Pairing Zigbee devices
Pairing can be easily accomplished using the web frontend to Zigbee2MQTT. 
The web frontend can be found by pointing a web browser to the IP address 
of the Raspberry Pi and the port number specified in the `configuration.yml` file 
(port 8081 in the example file above). In the web frontend, click the button 
labelled `Permit join (All)`. Once this button is clicked a countdown will 
proceed during which time new devices can be paired to the Zigbee network 
(typically the countdown lasts for 255 seconds).

Typically a new device is paired by performing a factory reset of the device.
The way to perform a factory reset varies by device type and manufacturer. 
For example, Ikea Tradfri bulbs can be factory reset by toggling the power 6 times
and Ikea Tradfri outlets can be factory reset using a reset button in a small pinhole.
A few moments after reseting a device, the web frontend should report the pairing of the device. 
Clicking on the devices heading in the web frontend should display a list of paired devices 
along with each manufacturer, model, and IEEE address. The web frontend provides many nifty 
features like displaying a network map and the ability to perform updates on connected devices.

In addition to the IEEE address each Zigbee device has a "friendly name."
By default, the "friendly name" is initialized to the IEEE address, but
it is recommended that you assign a more meaningful "friendly name" using the web frontend. 
For example, a bulb could be named "bulb1" or "porch light".
This allows devices to be controlled and referenced using a *name* rather than
relying on a cumbersome IEEE address. Keep a list of the "friendly names" since
these will later need to be included in the home-sense configuration file.

### Binding Zigbee Devices
One helpful feature of Zigbee networks is the ability to *bind* devices. This feature allows
devices to directly control each other. For example, a switch (such as this 
[IKEA E1743](https://www.zigbee2mqtt.io/devices/E1743.html))
can bind to an outlet or bulb so that it can be controlled directly by the switch. 
This can be configured in the Zigbee2MQTT web frontend using the `bind` tab shown
in the device view. For example, to control a device like a bulb or an outlet with a switch, 
bind the switch to the corresponding device. Home-sense can control lights and outlets
at preset times, but binding a switch enables the device to be manually controlled as well.

## Notes on Controlling Zigbee devices over MQTT
Once devices have been paired, they can be controlled simply by sending 
specially crafted MQTT messages. These messages must be published to the topic
`zigbee2mqtt/FRIENDLY_NAME/set` where `FRIENDLY_NAME` is the friendly name for a device. 
In the case of a bulb or smartplug, sending a message of "ON"
or "OFF" to the appropriate topic for the device will turn the device on or off.

Test MQTT messages can be sent from the command line on the Raspberry Pi using tools included with 
with the mosquitto package. For example, to turn on a light bulb with the friendly name of "bulb1" using the mostquitto client tool, type:
```
mosquitto_pub -h 127.0.0.1 -t zigbee2mqtt/bulb1/set -m "ON"
```
where `127.0.0.1` is the local loopback address to connect to the local MQTT broker and 
`zigbee2mqtt/bulb1/set` is the MQTT topic to control the settings for
the device with the friendly name `bulb1`. 

By subscribing the MQTT topic for a sensor you can receive updates from a sensor.
Consult the Zigbee2MQTT documentation for a [complete list of MQTT topics and
messages](https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html).

## Setting up the Python control software
Once Zigbee2MQTT is installed and devices are successfully paired we can setup the
`home-sense` control program itself. This program communicates with Zigbee devices by 
sending messages to the MQTT broker which are then bridged to the Zigbee network via Zigbee2MQTT.
The control program is written in Python version 3 and uses the 
[paho-mqtt](https://www.eclipse.org/paho/index.php?page=clients/python/index.php) library to send
MQTT messages. The dependencies for `home-sense` can all be installed from the command-line as follows:
```
$ pip3 install configparser paho-mqtt sqlite3 smtplib astral flask waitress
```
The Python program assumes [zigbee2mqtt](https://www.zigbee2mqtt.io/) is installed to 
provide a bridge to the zigbee network sensors (as described above). `zigbee2mqtt` supports a
variety of [sensors](https://www.zigbee2mqtt.io/supported-devices/), however, with some sensors your mileage may vary.

This project uses [flask](https://flask.palletsprojects.com) to provide a local accessible 
webpage to display sensor values. Flask’s built-in development WSGI server is 
[not designed to be particularly efficient, stable, or secure](https://flask.palletsprojects.com/en/master/server/)
so this project uses the [waitress](https://github.com/Pylons/waitress) server instead.
The web server runs on port 8080 by default (hence the Zigbee2MQTT web front end is 
configured to run on port 8081 to avoid a port conflict).
The home-sense webpage includes javascript code that uses the [plotly](https://plotly.com/) 
library to plot a chart of sensor values collected over the last day, month, and year which
are stored in a SQLite database file.
The home-sense `templates` folder should be installed with the Python program since it is 
required for the web interface. 

Finally, this project requires access to an SMTP server to send e-mail alerts.
The program can send mail using a local SMTP server or 
[Postfix](https://www.postfix.org/BASIC_CONFIGURATION_README.html) can be configured on the 
localhost to relay mail to another SMTP server. Postfix can be setup to handle secure SASL 
authenticated communucations which are required by many SMTP servers.
Note that some ISPs may require that you adjust your mail settings to allow for external email clients.

## Configuration
Home-sense includes a `home-sense.conf` configuration file which should be adjusted to reflect 
your local settings. In particular, you will need to specify the "friendly names" of any Zigbee
sensors, lights, and outlets you are using along with the IP Address of the MQTT broker for 
reaching the Zigbee network (ideally the broker will be run on the local host).
Furthermore, you should set your city so that the dusk time can be properly computed.
The configuration file includes email settings as well as the thresholds at which e-mail 
alerts should be triggered. 
It also includes settings for the MQTT and Web ports as well as the name and location of 
a log file. By default, a log file named `home-sense.log` will be written in the same 
folder where the program resides.

## Launching the program
The program can be launched from the command-line in the installation folder as follows:
```
python3 home-sense.py
```
If the `home-sense` program is launched at boot time, it should be started only *after* the network is up and running.
One way to ensure this is to launch the program as a systemd service which is configured to wait
for the network to come online 
([see the example of of using systemd with Zigbee2MQTT](https://www.zigbee2mqtt.io/guide/installation/01_linux.html#optional-running-as-a-daemon-with-systemctl)).

Once the program is running you can access the web front end by pointing your browser to:
```
http://a.b.c.d.:8080
```
where `a.b.c.d` is the IP address of the Raspberry Pi and `8080` is the web server port configured
in the `home-send.conf` file (set to 8080 by default). The web service provides friendly web pages
for viewing the status, sensor history, and adjusting the settings for the home-sense program.


## Security considerations
This should be run on a secure local network since the web pages are open and unencrypted.
The logfile is also accessible via the web interface.

This program is intended to be run on a private home network and is provided "as is" without any 
warranty, expressed or implied, about merchantability or fitness for a particular purpose. 
*Your mileage may vary*.
