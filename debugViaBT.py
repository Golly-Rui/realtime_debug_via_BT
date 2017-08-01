import serial
import serial.tools.list_ports
import logging
import time
import struct
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import threading
import re

__author__ = 'Guoli LV'
__email__ = 'guoli-lv@hotmail.com'


class DebugViaBT():
    AT_INQ = b'AT+INQ?\r\n'
    AT_CHECK = b'AT\r\n'
    AT_OK = b'OK\r\n'
    AT_STATE = b'AT+STATE?\r\n'
    AT_CONNECTED = b'+STATE:CONNECTED\r\n'
    AT_CONNECT = b'AT+LINK=ba,55,57083C\r\n'
    pdColumns = ['timestamp','tick','measured','setpoint','kp','ki','kd']
    buffer = pd.DataFrame()
    changing = False
    stopped = False
    kp = None
    ki = None
    kd = None
    setpoint = None

    def __init__(self, dev=None,interactivePlot=False,interactiveSend=False):
        '''

        :param dev: serial port, when None is passed, a prompt that asks users to choose serial port will be showed.
        :param interactive: Enable real time plotting, otherwise figure will be showed when keyboardInterrupt occurs.
        :param interactiveSend: Enable interactive shell to send PID and setpoint with input().
        '''
        super(DebugViaBT, self).__init__()

        self.serLock = threading.Lock()
        self.interactivePlot = interactivePlot
        self.interactiveSend = interactiveSend

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

        if self.interactivePlot is True:
            self.fig= plt.figure()
            self.ax = self.fig.add_subplot(111)
            self.plot = plt.Line2D((None,),(None,))
            self.ax.add_line(self.plot)
            self.fig.canvas.draw()
            plt.show(block=False)

        # Start __receive_loop
        threads = list()
        threads.append(threading.Thread(target=self.__receive_loop))
        # threads.append(threading.Thread(target=self.input_new_value))
        for t in threads:
            t.setDaemon(True)
            t.start()

    def __receive_loop(self):
        buffer = b''
        while self.stopped is False:
            buffer = buffer + self.ser.read_all()
            result = re.search( b'PID[\s\S]{24}\r\n',buffer)
            if result is not None:
                try:
                    # tick(uint64),measured(float),setpoint(float),kp(float),ki(float),kd(float)
                    structure = list(struct.unpack('<Ifffff',result.string[result.start()+3 : result.end()-2]))
                    structure.insert(0,time.time())
                    dataPack = pd.DataFrame([structure],columns = self.pdColumns,dtype=pd.np.float32)

                    # TODO Received data validation

                    # TODO Compressed PID values validation

                    # If PID and setpoint values stored in this object differs from remote device,
                    # then we should update the values in the remote one.
                    # However, when PID values stored are None,
                    # which means we haven't set PID values in this item yet,
                    # we should update these ones with remote ones.
                    if self.kp is None:
                        self.kp = dataPack['kp'].item()
                        self.ki = dataPack['ki'].item()
                        self.kd = dataPack['kd'].item()
                        self.setpoint = dataPack['setpoint'].item()
                        if self.interactivePlot is True:
                            self.ax.set_title('Setpoint Kp Ki Kd\n%s'% dataPack[['setpoint','kp','ki','kd']].to_string(header=False, index=False))
                    elif not pd.np.isclose(self.kp,dataPack['kp'].item()) or not pd.np.isclose(self.ki,dataPack['ki'].item()) or not pd.np.isclose(self.kd,dataPack['kd'].item()) or not pd.np.isclose(self.setpoint,dataPack['setpoint'].item()):
                        self.changing = True
                        self.__transfer_thread(self.kp,self.ki,self.kd,self.setpoint)
                    elif self.changing is True:
                        self.changing = False
                        self.buffer = pd.DataFrame()
                        if self.interactivePlot is True:
                            self.ax.set_title('Kp Ki Kd Setpoint\n%s'% dataPack[['kp','ki','kd','setpoint']].to_string(header=False, index=False))

                    dataPack['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(dataPack['timestamp'][0]))
                    self.buffer = self.buffer.append(dataPack)

                    if self.interactivePlot is True:
                        err = self.buffer['measured'] - self.buffer['setpoint']
                        if len(err) >1:
                            self.plot.set_data(self.buffer['tick'],err)
                            # plt.pause(0.01)
                            self.ax.set_xlim(self.buffer['tick'].min(),self.buffer['tick'].max())
                            self.ax.set_ylim(err.min(),err.max())
                            self.fig.canvas.draw()
                    else:
                        print(dataPack.to_string(header=False, index=False),end='\r',flush=True)
                except struct.error as e:
                    self.logger.info('Invalid data (Length:%d): %s Error:%s'%(len(buffer),str(buffer),str(e)))
                finally:
                    buffer = buffer[result.end():]

    def __transfer(self,kp,ki,kd,setpoint):
        send = b"PID" + struct.pack('<ffff', kp, ki, kd, setpoint) + b'\r\n'
        self.serLock.acquire()
        self.ser.write(send)
        self.logger.info("Sending: %s" % send)
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
            # exit infinite loop

            # Signal thread to stop
            self.stopped = True

            if self.interactivePlot is False:
                try:
                    self.buffer['err'] = self.buffer['measured'] - self.buffer['setpoint']
                    self.buffer.plot.line('tick','err',title='')
                    self.logger.info("Err mean:%f"%self.buffer['err'].mean())
                    plt.show()
                except KeyError:
                    pass


            # b'PID' + struct.pack('<ffff',self.kp,self.ki,self.kd,self.target) +b'\r\n'
if __name__ == "__main__":
    debugViaBT = DebugViaBT(dev='/dev/ttyUSB0',interactiveSend=True,interactivePlot=True)
    # debugViaBT.receive_loop()
    debugViaBT.input_new_value()
    # while True:
        # time.sleep(0.1)

