# Home-sense program for use with Zigbee devices and a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import logging
from datetime import datetime
import smtplib
from email.utils import make_msgid
from email.mime.text import MIMEText

class Mail:
    ''' Class to encapsulate methods to send an alert email
        Assumes an SMTP server is available.
    '''
    def __init__(self, from_address, to_address, server):
        ''' Function to send a warning email - assumes server running locally to forward mail
        '''
        self.to_address = to_address        
        self.from_address = from_address
        self.server = server

    def send(self, subject, message):
        ''' Function to send an email - requires SMTP server to forward mail
        '''
        # message to be sent
        msg = MIMEText(message)
        msg['To'] = self.to_address
        msg['From'] = self.from_address
        msg['Subject'] = subject
        msg['Message-ID'] = make_msgid()

        # send the mail and terminate the session
        try:
            # creates SMTP session and send mail
            s = smtplib.SMTP(self.server)
            s.sendmail(self.from_address, self.to_address, msg.as_string())
            logging.info(f'{datetime.now()}: Email alert sent to {self.to_address}')
        except smtplib.SMTPResponseException as e:
            logging.info(f'{datetime.now()}: Email failed to send')
            logging.info(f'SMTP Error code: {e.smtp_code} - {e.smtp_error}')
        finally:
            s.quit()
