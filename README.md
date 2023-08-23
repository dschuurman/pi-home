# Pi-Home

Pi-Home is a home automation program using a Raspberry Pi connected to smart bulbs, smart outlets,
and a variety of sensors connected over a [Zigbee](https://en.wikipedia.org/wiki/Zigbee) wireless network.
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
(32-bit or 64-bit) and written in Python version 3. 
The code relies heavily on [Zigbee2MQTT](https://www.zigbee2mqtt.io/)
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
sudo apt-get install -y npm git make g++ gcc
```
Unfortunately, the Raspberry Pi repos may have an older version of the nodejs package,
and Zigbee2MQTT requires a recent version of nodejs. You can add the repository and install a
recent version of nodejs as follows:
```
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install nodejs
```
Once the dependencies are installed, Zigbee2MQTT can be installed from github by typing the 
following commands:
```
sudo mkdir /opt/zigbee2mqtt
sudo chown -R ${USER}: /opt/zigbee2mqtt
git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git /opt/zigbee2mqtt
cd /opt/zigbee2mqtt
npm ci
```
Note that the `npm ci` may produce some warnings which can be ignored.

Zigbee2MQTT requires a [YAML](https://en.wikipedia.org/wiki/YAML) configuration file which
may be edited by typing:
```
sudo nano /opt/zigbee2mqtt/data/configuration.yaml
``` 
Edit the configuration file so that it includes the following settings:
```
homeassistant: false
permit_join: true

# MQTT settings
mqtt:
  base_topic: zigbee2mqtt
  server: 'mqtt://127.0.0.1'

# Location of Zigbee USB adapter
serial:
  port: /dev/ttyACM0

# use a custom network key
advanced:
    network_key: GENERATE

# Start web frontend
frontend:
  port: 8081

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
>
> Note that the `frontend` setting provides a web frontend for viewing the Zigbee
network running on the specified port. While this can be useful for
setup and debugging, you may wish to disable it later.
>
> It is recommended to enable over-the-air (OTA) updates for all devices to keep them up-to-date.

Once the setup and configuration are complete, ensure the Zigbee USB adapter
is inserted in the Raspberry Pi and start Zigbee2MQTT as follows:
```
cd /opt/zigbee2mqtt
npm start
```
This will build and launch `zigbee2mqtt` from the command-line. Once the
it builds and launches successfully, you can exit the program by hitting ctrl-c.
To launch automaticlaly on boot under Linux, 
[setup Zigbee2MQTT to run using systemctl](https://www.zigbee2mqtt.io/guide/installation/01_linux.html#starting-zigbee2mqtt).
For more detailed informatoin about installing Zigbee2MQTT, refer to the official
[Zigbee2MQTT installation instructions](https://www.zigbee2mqtt.io/guide/installation/01_linux.html#installing).

## Setup a Zigbee Network of Devices
Next, we need to establish a network of Zigbee devices by pairing each new device 
with the Zigbee hub on the Raspberry Pi. Zigbee2MQTT supports a plethora of Zigbee devices 
and a [friendly device webpage](https://www.zigbee2mqtt.io/supported-devices/)
includes notes on compatibility, pairing, and details on what values are exposed.

### Pairing Zigbee devices
Pairing can be easily accomplished using the web frontend to Zigbee2MQTT. 
The web frontend can be found by pointing a web browser to the IP address 
of the Raspberry Pi and the port number specified in the `configuration.yaml` file 
(port 8081 in the example file above). In the web frontend, click the `Devices` tab and 
then the button labelled `Permit join (All)`. Once this button is clicked a countdown will 
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

In addition to the IEEE address each Zigbee device may be configured with a "friendly name."
By default, the "friendly name" is initialized to the IEEE address, but
it is recommended that you assign a more meaningful "friendly name" using the web frontend. 
For example, a bulb could be named "bulb1" or "porch light".
This allows devices to be controlled and referenced using a *name* rather than
relying on a cumbersome IEEE address. Keep a list of the "friendly names" since
these will later need to be included in the pi-home configuration file.

### Binding Zigbee Devices
One helpful feature of Zigbee networks is the ability to *bind* devices. This feature allows
devices to directly control each other. For example, a switch (such as this 
[IKEA E1743](https://www.zigbee2mqtt.io/devices/E1743.html))
can bind to an outlet or bulb so that it can be controlled directly by the switch. 
This can be configured in the Zigbee2MQTT web frontend using the `bind` tab shown
in the device view. For example, to control a device like a bulb or an outlet with a switch, 
bind the switch to the corresponding device. Pi-Home can control lights and outlets
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
`pi-home` control program itself. This program communicates with Zigbee devices by 
sending messages to the MQTT broker which are then bridged to the Zigbee network via Zigbee2MQTT.
The control program is written in Python version 3 and uses the 
[paho-mqtt](https://www.eclipse.org/paho/index.php?page=clients/python/index.php) library to send
MQTT messages. The dependencies for `pi-home` can all be installed from the command-line as follows:
```
sudo apt-get install python3-pip
pip3 install configparser paho-mqtt astral flask waitress
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
The pi-home sensor webpage includes javascript code that uses the [plotly](https://plotly.com/) 
library to plot a chart of sensor values collected over the last day, month, and year which
are stored in a SQLite database file.
The pi-home `templates` folder should be installed with the Python program since it is 
required for the web interface. 

Finally, this project requires access to an SMTP server to send e-mail alerts.
The program can send mail using a local SMTP server or 
[Postfix](https://www.postfix.org/BASIC_CONFIGURATION_README.html) can be configured on the 
localhost to relay mail to another SMTP server. Postfix can be setup to handle secure SASL 
authenticated communucations which are required by many SMTP servers.
Note that some ISPs may require that you adjust your mail settings to allow for external email clients.

## Configuration
Pi-Home includes a `pi-home.conf` configuration file which should be adjusted to reflect 
your local settings. In particular, you will need to specify the "friendly names" of any Zigbee
sensors, lights, and outlets you are using along with the IP Address of the MQTT broker for 
reaching the Zigbee network (ideally the broker will be run on the local host).
Furthermore, you should set your city so that the dusk time can be properly computed.
The configuration file includes email settings as well as the thresholds at which e-mail 
alerts should be triggered. 
It also includes settings for the MQTT and Web ports as well as the name and location of 
a log file. By default, a log file named `pi-home.log` will be written in the same 
folder where the program resides.

## Launching the program
The program can be launched from the command-line from the installation folder as follows:
```
python3 pi-home.py
```
The `pi-home` program may also be automatically launched at boot time as a systemd service.
This service must be configured to wait for the network to come online before starting.
This can be configured by creating a systemd service file in `/etc/systemd/system/pi-home.service` 
with the following settings:
```
[Unit]
Description=pi-home
After=network-online.target
[Service]
ExecStart=/bin/sh -c "/usr/bin/python3 pi-home.py"
WorkingDirectory=/home/pi/pi-home
Restart=always
User=pi
[Install]
WantedBy=multi-user.target
```
Note that the `User` and `WorkingDirectory` will need to be set to reflect
your default username and the directory where the pi-home source files are installed.
Finally, enable the pi-home service as follows:
```
sudo systemctl enable pi-home.service
```
Reboot the computer and ensure that the service is started as expected. To check the status
of the service, type:
```
sudo systemctl status pi-home.service
```
Once the program is running, you should be able to access the web interface by pointing your browser to:
```
http://a.b.c.d.:8080
```
where `a.b.c.d` is the IP address of the Raspberry Pi and `8080` is the web server port configured
in the `home-send.conf` file (set to 8080 by default). The web service provides friendly web pages
for viewing the status, sensor history, and adjusting the settings for the pi-home program.


## Security considerations
This should be run on a secure local network since the web pages are open and unencrypted.
The logfile is also accessible via the web interface.

This program is intended to be run on a private home network and is provided "as is" without any 
warranty, expressed or implied, about merchantability or fitness for a particular purpose. 
*Your mileage may vary*.
