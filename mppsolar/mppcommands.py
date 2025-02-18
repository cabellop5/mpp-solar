"""
MPP Solar Inverter Command Library
reference library of serial commands (and responses) for PIP-4048MS inverters
mppcommands.py
"""

import serial
import time
import re
import logging
import json
import glob
import os
# from pprint import pprint
from os import path
from argparse import ArgumentParser

from .mppcommand import mppCommand

logger = logging.getLogger()


class MppSolarError(Exception):
    pass


class NoDeviceError(MppSolarError):
    pass


class NoTestResponseDefined(MppSolarError):
    pass


# Read in all the json files in the commands subdirectory
# this builds a list of all valid commands
COMMANDS = []
here = path.abspath(path.dirname(__file__))
files = glob.glob(here + '/commands/*.json')
for file in sorted(files):
    with open(file) as f:
        try:
            data = json.load(f)
        except Exception as e:
            print("Error processing JSON in {}".format(file))
            print(e)
        # print("Command: {} ({}) - expects {} response(s) [regex: {}]".format(data['name'], data['description'], len(data['response']), data['regex']))
        if data['regex']:
            regex = re.compile(data['regex'])
        else:
            regex = None
        COMMANDS.append(mppCommand(data['name'], data['description'], data['type'], data['response'], data['test_responses'], regex))


def trunc(text):
    """
    Truncates / right pads supplied text
    """
    if len(text) >= 30:
        text = text[:30]
        return '{:<30}...'.format(text)
    return '{:<30}   '.format(text)


def getKnownCommands():
    """
    Provides a human readable list of all defined commands
    """
    msgs = []
    msgs.append('-------- List of known commands --------')
    for cmd in COMMANDS:
        msgs.append('{}: {}'.format(cmd.name, cmd.description))
    return msgs


def getCommand(cmd):
    """
    Returns the mppcommand object of the supplied cmd string
    """
    logging.debug("Searching for cmd '{}'".format(cmd))
    for command in COMMANDS:
        if not command.regex:
            if cmd == command.name:
                return command
        else:
            match = command.regex.match(cmd)
            if match:
                logging.debug(command.name, command.regex)
                logging.debug("Matched: {} Value: {}".format(command.name, match.group(1)))
                command.set_value(match.group(1))
                return command
    return None


class mppCommands:
    """
    MPP Solar Inverter Command Library
    """

    def __init__(self, serial_device=None, baud_rate=2400):
        if (serial_device is None):
            raise NoDeviceError("A device to communicate by must be supplied, e.g. /dev/ttyUSB0")
        self._baud_rate = baud_rate
        self._serial_device = serial_device

    def getKnownCommands(self):
        """
        Return list of defined commands
        """
        return getKnownCommands()

    def doSerialCommand(self, command):
        """
        Opens serial connection, sends command (multiple times if needed)
        and returns the response
        """
        response_line = None
        logging.debug('port %s, baudrate %s', self._serial_device, self._baud_rate)
        if (self._serial_device == 'TEST'):
            # Return a valid response if _serial_device is TEST
            # - for those commands that have test responses defined
            # print "TEST"
            # print command.get_test_response()
            command.set_response(command.get_test_response())
            return command
        if (self._serial_device == '/dev/hidraw0'):
            usb0 = os.open('/dev/hidraw0', os.O_RDWR | os.O_NONBLOCK)
            response = ""
            for x in (1, 2, 3, 4):
                command_crc = command.full_command

                if len(command_crc) < 9:
                    time.sleep(0.35)
                    os.write(usb0, command_crc)
                else:
                    cmd1 = command_crc[:8]
                    cmd2 = command_crc[8:]
                    time.sleep(0.35)
                    os.write(usb0, cmd1)
                    time.sleep(0.35)
                    os.write(usb0, cmd2)
                    time.sleep(0.25)

                while True:
                    time.sleep(0.15)
                    r = os.read(usb0, 256)
                    response += r
                    if '\r' in r: break

            logging.debug('usb response was: %s and is valid', response_line, command.is_response_valid(response))
            print(response)
            if command.is_response_valid(response):
                command.set_response(response)
                # return response without the start byte and the crc
                return command

            logging.critical('Command execution failed')
            return None

        with serial.serial_for_url(self._serial_device, self._baud_rate) as s:
            # Execute command multiple times, increase timeouts each time
            for x in (1, 2, 3, 4):
                logging.debug('Command execution attempt %d...', x)
                s.timeout = 1 + x
                s.write_timeout = 1 + x
                s.flushInput()
                s.flushOutput()
                s.write(command.full_command)
                time.sleep(0.5 * x)  # give serial port time to receive the data
                response_line = s.readline()
                logging.debug('serial response was: %s', response_line)
                if command.is_response_valid(response_line):
                    command.set_response(response_line)
                    # return response without the start byte and the crc
                    return command
            logging.critical('Command execution failed')
            return None

    def execute(self, cmd):
        """
        Sends a command (as supplied) to inverter and returns the raw response
        """
        command = getCommand(cmd)
        if command is None:
            logging.critical("Command not found")
            return None
        else:
            logging.debug("Command valid {}".format(command.name))
            logging.debug('called: execute with query %s', command)
            return self.doSerialCommand(command)


if __name__ == '__main__':
    parser = ArgumentParser(description='MPP Solar Command Utility')
    parser.add_argument('-c', '--command', help='Command to run', default='QID')
    args = parser.parse_args()

    logger = logging.getLogger('Mpp Logger')
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    fh = logging.FileHandler('/var/www/py-mpp-solar/mppsolar.log')
    fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    # add the handlers to logger
    logger.addHandler(ch)
    logger.addHandler(fh)
    #
    # logging.basicConfig(filename='/var/www/py-mpp-solar/mppsolar.log', level='DEBUG')
    #
    # console = logging.StreamHandler()
    # console.setLevel(logging.DEBUG)
    # formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    # console.setFormatter(formatter)
    # logging.getLogger('').addHandler(console)

    mp = mppCommands("TEST")
    cmd = mp.execute(args.command)
    print("response: ", cmd.response)
    # print len(cmd.response_definition)
    print("valid? ", cmd.valid_response)
    print("response_dict: ", cmd.response_dict)
    # for line in getKnownCommands():
    #    print line
