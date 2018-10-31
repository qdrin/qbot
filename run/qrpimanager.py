#!/usr/bin/python3
import sys, os
from datetime import datetime
import sqlite3
import RPi.GPIO as GPIO
from qbasemanager import QBaseManager
#from multiprocessing import Pipe

"""Test environmetn creation:
1. ds-1820 sensors emulation
    - create file /sys/bus/w1/devices/[sensor_id]/w1_slave for each sensor in config. Or create symlink
    - write a test stuff there (without tabs of course): 
            50 05 4b 46 1f ff 1f 10 35 : crc=35 YES
            50 05 4b 46 1f ff 1f 10 35 t=85000
2. GPIO emulation:
    - copy recursive RPi test directory to current qrpimanager.py location
3. codesend emulation (RF433 devices):
    - copy 'codesend' bash script to 'executable' path of codesend (get it from config). Or create symlink to it
"""

class QRpiManager(QBaseManager):
    def __init__(self, **config):
        QBaseManager.__init__(self, **config)
        self.codesend_path = self.config['executables']['codesend']
        self.sensors = config['sensors']
        self.radios433 = config['radios433']
        self.db = config['db']
        self.db_path = self.db['file']
        self.sensors_data_table = self.db['tables']['sensors_data']
        #Init relays section
        relays = config['relays']
        self.relays = []
        try:
            GPIO.setmode(GPIO.BCM) #Set gpio mode to 'BCM' (bcm pin-numbers are treated)
        except Exception as err:
            l_err = 'Init GPIO failed: %s' % err
            self.errors.append(l_err)
            self.logger.error(l_err)
            relays = []
        for relay in relays:
            try:
                relay['state'] = self.init_pin(relay['bcmid'], relay['initmode'], relay['initstate'])
                self.relays.append(relay)
            except Exception as err:
                l_err = "Init relay %s failed: %s" % (relay['id'], err)
                self.logger.error(l_err)
                self.errors.append(l_err)
        self.logger.info('Init completed. %d/%d relays, %d/%d sensors, %d/%d 433-Mhz radios' % (len(self.relays), len(relays), len(self.sensors), \
                                                                                                len(config['sensors']), len(self.radios433), len(config['radios433'])))
        
    #Inits the GPIO pin. Usually for connected relays
    def init_pin(self, pinnum, mode, state = 0):
        GPIO.setup(pinnum, mode)
        GPIO.output(pinnum, state)
        return state
    
    #process function is calling at every run() cycle
    def process(self):
        #reading sensors and saving their values if updateinterval is passed
        for sensor in self.sensors:
            tstamp = sensor['lastupdate']
            #If field is empty or unknown type
            if str(type(tstamp)) != "<class 'float'>":
                tstamp = 0.0
            sensor['lastupdate'] = datetime.now().timestamp()
            try:
                sensor['value'] = self.get_ds_temperature(sensor['path'])
            except Exception as err: #if operation failed, sensors value is set to the error text
                l_err = "Read sensor %s failed: %s" % (sensor['id'], err)
                self.errors.append(l_err)
                sensor['value'] = l_err
            #'updateinterval' defines the time in seconds between inserting current sensor values in DB
            if sensor['updateinterval'] > 0 and (sensor['lastupdate'] - tstamp) > sensor['updateinterval']:
                self.insert_sensor_data(sensor['id'], sensor['value'])

    #Reads the temperature value of Dallas Semiconductors sensor
    def get_ds_temperature(self, sensor_path):
        res = None
        tfile = open(sensor_path)
        ttext = tfile.read()
        tfile.close()
        res = '{:.1f}'.format(int(ttext.split("\n")[1].split("=")[1])/1000)
        return res

    #Sends ruling code by the RF433 transmitter (commonly for radio-outlets)
    def radio_send(self, code):
        os.system('%s %s' % (self.codesend_path, code))
        return "OK. Code sent: %s" % code

    def getSensor(self, id_list):
        if len(id_list) == 0:
            sensors = self.sensors
        else:
            sensors = list(filter(lambda x: x['id'] in id_list, self.sensors))
        res = 'Датчиков %d:' % len(sensors)
        for sensor in sensors:
            try:
                res = "%s\n%s: %s" % (res, sensor['id'], self.get_ds_temperature(sensor['path']))
            except Exception as err: #if operation failed, sensors value is set to the error text
                l_err = "Read sensor %s failed: %s" % (sensor['id'], err)
                self.logger.error(l_err)
                res = "%s\n%s: %s" % (res, sensor['id'], err)
                sensor['value'] = l_err
        return res
    
    def setRadio(self, id, mode):
        res = ''
        try:
            radio = list(filter(lambda x: x['id'] == id, self.radios433))[0]
            if mode:
                code = radio['code_on']
            else:
                code = radio['code_off']
        except Exception as err:
            res = 'Bad radio ID=%s: %s' % (id, err)
            self.logger.error(res)
            return res
        try:
            res = self.radio_send(code)
            radio['lastcommand'] = mode
        except Exception as err:
            res = "send code failed: %s" % err
        return res
    
    #returns last code sent to radio433 with ID
    def getRadio(self, id):
        try:
            radio = list(filter(lambda x: x['id'] == id, radios433))[0]
            res = "Last state sent to %s: %s" % (id, radio['lastcommand'])
        except Exception as err:
            res = "Bad radio ID=%s: %s" % (id, err)
        return res

    def setRelay(self, id_list, mode):
        relays = list(filter(lambda x: x['id'] in id_list, self.relays)) if len(id_list) else self.relays
        res = '%d relays:' % len(relays)
        for relay in relays:        
            try:
                pin = relay['bcmid']
                relay['state'] = self.set_pin(pin, mode)
                res = "%s\nРеле %s: %s" % (res, relay['id'], relay['state'])
            except Exception as err:
                r = "Реле %s: failed" % (relay['id'])
                res = "%s\n%s" % (res, r)
                self.logger.error(res)
        return res

    #Set the pin state. Relay ON/OFF
    def set_pin(self, pinnum, state):
        GPIO.output(pinnum, state)
        return state
    
    def getRelay(self, id_list = []):
        relays = list(filter(lambda x: x['id'] in id_list, self.relays)) if len(id_list) else self.relays
        res = '%d relays:' % len(relays)
        for relay in relays:
            try:
                pin = relay['bcmid']
                relay['state'] = GPIO.input(pin)
                res = "%s\nРеле %s: %s" % (res, relay['id'], relay['state'])
            except Exception as err:
                res = "%s\nRelay %s get failed: %s" % (res, id, err)
        return res

    def insert_sensor_data(self, sensor_id, data):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        now = str(datetime.now()).split('.')[0]
        cur.execute("INSERT INTO %s (sensor_id, result, fill_date) VALUES (%d, '%s', '%s')" % (self.sensors_data_table, sensor_id, str(data), now))
        conn.commit()
        conn.close()



