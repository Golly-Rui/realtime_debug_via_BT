import serial
import serial.tools.list_ports
import logging
import time
import struct
import pandas as pd
import sqlite3

__author__ = 'Guoli LV'
__email__ = 'guoli-lv@hotmail.com'


class DebugViaBT():
    AT_INQ = b'AT+INQ?\r\n'
    AT_CHECK = b'AT\r\n'
    AT_OK = b'OK\r\n'
    AT_STATE = b'AT+STATE?\r\n'
    AT_CONNECTED = b'+STATE:CONNECTED\r\n'
    AT_CONNECT = b'AT+LINK=ba,55,57083C\r\n'
    pdColumns = ['timestamp','pitch','kp','ki','kd']

    def __init__(self, dev='/dev/ttyUSB0'):
        super(DebugViaBT, self).__init__()

        # Perform check on system platform

        log_fmt = "[%(msecs)s][%(levelname)s] %(message)s"
        formatter = logging.Formatter(log_fmt)
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        self.logger = logging.getLogger("DebugViaBT")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)

        self._database = sqlite3.connect('bluetooth.db')

        # Prompt to select serial port
        self.ports = serial.tools.list_ports.comports()
        listToShow = ['Device:%s\tDescription:%s'%(port.device,port.description) for port in self.ports]
        for index in range(len(listToShow)):
            listToShow[index]='%d\t%s'%(index,listToShow[index])
        [print(device) for device in listToShow]

        devIndex = int(input('Select device:'))
        self.device = self.ports[devIndex]
        print('Device selected:%s'%self.ports[devIndex].device)
        dev = self.device.device

        self.ser = serial.Serial(dev, baudrate=115200, timeout=1)
        if not self.ser.is_open:
            self.ser.open()
        while True:
            print("Please keep pressing button to keep in AT mode.")
            time.sleep(1)
            self.ser.write(self.AT_CHECK)
            received = self.ser.readline()
            # If we received nothing
            if received is b'':
                self.logger.error("Received nothing. Please check connection.")
            elif received == self.AT_OK:
                self.logger.info("Successfully connect to BT via AT command.")
                break
            else:
                self.logger.error("Received:%s" % received)

        # Inquiry
        # self.ser.write(self.AT_INQ)

        # Searching
        # print("Searching for 5 second...")
        # time.sleep(5)
        # inq = self.ser.read_all()
        # print(inq)

        self.ser.write(self.AT_STATE)
        received = self.ser.readline()
        if received == self.AT_CONNECTED:
            self.logger.info("Already connected to slave BT device.")
        else:
            # Connect
            self.ser.write(self.AT_CONNECT)
            self.logger.info("Connecting...")
            time.sleep(3)
            received = self.ser.readline()
            if received == self.AT_OK:
                self.logger.info("Successfully connect to slave BT device.")
            else:
                self.logger.error("Received: %s" % (str(received)))

    def loop(self):
        while(True):
            received = self.ser.readline()
            if received is b'':
                continue
            if received[-2:] == b'\r\n':
                pd.DataFrame([struct.unpack('<Iffff',received[0:-2])],columns = self.pdColumns)

if __name__ == "__main__":
    debugViaBT = DebugViaBT()
