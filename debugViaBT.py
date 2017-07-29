import serial
import serial.tools.list_ports
import logging
import time
import struct
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import threading
import queue

__author__ = 'Guoli LV'
__email__ = 'guoli-lv@hotmail.com'


class DebugViaBT():
    AT_INQ = b'AT+INQ?\r\n'
    AT_CHECK = b'AT\r\n'
    AT_OK = b'OK\r\n'
    AT_STATE = b'AT+STATE?\r\n'
    AT_CONNECTED = b'+STATE:CONNECTED\r\n'
    AT_CONNECT = b'AT+LINK=ba,55,57083C\r\n'
    pdColumns = ['timestamp','tick','pitch','setpoint','kp','ki','kd']
    buffer = pd.DataFrame()

    def __init__(self, dev='/dev/ttyUSB0',interactivePlot=False,interactiveSend=False):
        '''

        :param dev: serial port, when None is passed, a prompt that asks users to choose serial port will be showed.
        :param interactive: Enable real time plotting, otherwise figure will be showed when keyboardInterrupt occurs.
        :param interactiveSend: Enable interactive shell to send PID and setpoint with input().
        '''
        super(DebugViaBT, self).__init__()

        self.serLock = threading.Lock()
        self.interactivePlot = interactivePlot
        self.interactiveSend = interactiveSend
        self.tranferQueue = queue.Queue()
        self.stopped = False
        self.kp = None
        self.ki = None
        self.kd = None
        self.setpoint = None

        # Perform check on system platform

        log_fmt = "[%(msecs)s][%(levelname)s] %(message)s"
        formatter = logging.Formatter(log_fmt)
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        self.logger = logging.getLogger("DebugViaBT")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)

        self._database = sqlite3.connect('bluetooth.db')

        if dev is None:
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
            time.sleep(0.2)

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

        # Start __receive_loop
        t = threading.Thread(target=self.__receive_loop)
        t.setDaemon(True)
        t.start()

    def __receive_loop(self):
        fig = plt.figure()
        while self.stopped is False:
            received = self.ser.readline()
            if received is b'':
                continue
            if received[-2:] == b'\r\n':
                try:
                    # tick(uint64),pitch(float),setpoint(float),kp(float),ki(float),kd(float)
                    structure = list(struct.unpack('<Ifffff',received[0:-2]))
                    structure.insert(0,time.time())
                    dataPack = pd.DataFrame([structure],columns = self.pdColumns)
                    self.buffer = self.buffer.append(dataPack)
                    dataPack['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(dataPack['timestamp'][0]))

                    # If PID and setpoint values stored in this object differs from remote device,
                    # then we should update the values in the remote one.
                    # However, when PID values stored are None, which means we haven't set PID values in this item,
                    # we should update these ones with remote ones.
                    if self.kp != dataPack['kp'].item() or self.ki != dataPack['ki'].item() or self.kd != dataPack['kd'].item() or self.setpoint != dataPack['setpoint'].item():
                        if self.kp is None:
                            self.kp = dataPack['kp'].item()
                            self.ki = dataPack['ki'].item()
                            self.kd = dataPack['kd'].item()
                            self.setpoint = dataPack['setpoint'].item()
                        else:
                            self.__transfer_thread(self.kp,self.ki,self.kd,self.setpoint)

                except struct.error as e:
                    self.logger.info('Invalid data (Length:%d): %s Error:%s'%(len(received),str(received),str(e)))
                if self.interactivePlot is True:
                    # TODO interactive plotting
                    pass

    def __transfer(self,kp,ki,kd,setpoint):
        send = b"PID" + struct.pack('<ffff', kp, ki, kd, setpoint) + b'\r\n'
        self.serLock.acquire()
        self.ser.write(send)
        self.logger.info("Get %s" % send)
        self.serLock.release()

    def __transfer_thread(self,kp,ki,kd,setpoint):
        t = threading.Thread(target=self.__transfer,args=(kp,ki,kd,setpoint))
        t.setDaemon(True)
        t.start()

    def input_new_value(self):
        """
        """
        try:
            while True:
                if self.interactiveSend is True:
                    newValues = input("New PID and setpoint value(separated by space, can be float numbers):\n").split()
                    if len(newValues) != 4:
                        self.logger.error('New values should be 4 numbers like "1 2 3 4"')
                        continue
                    else:
                        try:
                            (self.kp,self.ki,self.kd,self.setpoint) = list(map(lambda x:float(x),newValues))
                            self.__transfer_thread(self.kp,self.ki,self.kd,self.setpoint)
                        except ValueError:
                            self.logger.logger('Input should be numbers.')
                else:
                    # TODO program takes control of changing PID in MCU
                    pass

        except KeyboardInterrupt as e:
            self.stopped = True
            # exit infinite loop
            if self.interactivePlot is False:
                try:
                    self.buffer['err'] = self.buffer['pitch'] - self.buffer['setpoint']
                    self.buffer.plot.line('tick','err',title='')
                    print("Err mean:%f"%self.buffer['err'].mean())
                    plt.show()
                except KeyError:
                    pass


            # b'PID' + struct.pack('<ffff',self.kp,self.ki,self.kd,self.target) +b'\r\n'
if __name__ == "__main__":
    debugViaBT = DebugViaBT(interactiveSend=True)
    # debugViaBT.receive_loop()
    debugViaBT.input_new_value()

