#!/usr/bin/python3
"""Base for qbot manager modules"""

from multiprocessing import Process, Pipe
import logging
from time import sleep
from datetime import datetime

class QBaseManager(Process):
    """Defines basic behaviour of manager module"""
    def __init__(self, **config):
        """Init, set logger, name, timeout, pipes and semaphores"""
        Process.__init__(self)
        #print(config)
        self.config = config
        self.logger = logging.getLogger(self.name)
        p_logger = self.config['logger'] #parent logger
        for h in p_logger.handlers:
            self.logger.addHandler(h)
        self.logger.setLevel(p_logger.level)
        self.logger.info('Init started')
        self.name = '%s_%s' % (self.name, self.config['name'])
        if 'timeout' in self.config.keys():
            self.timeout = self.config['timeout']
        else:
            self.timeout = 1
        #config must have 2 pipes and events
        # command_pipe: main module puts commands to it and the manager module puts responses
        self.command_pipe = config['command_pipe']
        # semaphore to indicate data available in command_pipe
        self.command_pipe_semaphore = config['command_pipe_semaphore']
        # alert_pipe: manager module puts alerts to it. No need in responses from main module
        self.alert_pipe = config['alert_pipe']
        # semaphore for alert_pipe
        self.alert_pipe_semaphore = config['alert_pipe_semaphore']
        self.alert_pipe_semaphore.clear()
        #initializing 'lastsent' field of triggers with None
        for trigger in self.config['triggers']:
            trigger['lastsent'] = None
        self.isWorking = True
        self.errors = [] #variable keeping errors occured. It's cleared every cycle turn
        #self.logger.debug(self.config)
        self.status = 'Init'
    
    def run(self):
        """Module func itself

        Every cycle it checks command semaphore for new commands and if it's set run command
        Then runs self.alert() function to check alert conditions
        
        """
        self.status = 'Running'
        while self.isWorking:
            self.errors = []
            sleep(self.timeout)
            try:
                self.process()
            except Exception as err:
                l_err = 'process() failed: %s' % err
                self.logger.error(l_err)
                self.errors.append(l_err)

            if self.command_pipe_semaphore.is_set(): #check if new command has come
                try:
                    cmd = self.command_pipe.recv()
                    self.command_pipe_semaphore.clear()
                except Exception as err:
                    l_err = 'command_pipe.recv() failed: %s' % err
                    self.logger.error(l_err)
                    self.errors.append(l_err)                
                if cmd:
                    l = locals()
                    command = 'resp = %s' % cmd
                    self.logger.debug(command)
                    try:
                        exec(command)
                        self.logger.debug('Response: %s' % l['resp'])
                        self.command_pipe.send(l['resp'])
                    except Exception as err:
                        l_err = "command failed: %s" % err
                        self.errors.append(l_err)
                        self.logger.error(l_err)
                        self.command_pipe.send(l_err)
            #alert should be at the end of cycle in the case of alerting of errors
            try:
                self.alert()
            except Exception as err:
                l_err = 'alert() failed: %s' % err
                self.logger.error(l_err)
                self.errors.append(l_err)            
        self.logger.info('Exit')
                
    #Checks the module triggers and send alerts to main module
    def alert(self):
        """Check alert conditions defined at module conf-file

        Conditions should be defined as one-line python statements and return True if we need to send alert
        If a condition is True and time interval from last alert is exceed 'interval' value predefined message will be sent

        """
        for trigger in self.config['triggers']:
            if trigger['lastsent']:
                if trigger['interval'] == 0 or (datetime.now() - trigger['lastsent']).seconds < trigger['interval']:
                    continue
            l = locals()
            exec('cond = %s' % trigger['condition'])
            if l['cond']:
                exec('msg = %s' % trigger['message'])
                self.sendMessage(l['msg'])
                trigger['lastsent'] = datetime.now()
    
    #sends message(alert) to the alert_pipe
    def sendMessage(self, message):
        """Puts message to alert_pipe. Main module should send it by default channel(s)"""
        if self.alert_pipe_semaphore.is_set():
            err = 'Alert pipe is busy'
            self.logger.error(err)
            self.errors.append(err)
        else:
            try: #We need this try cause the sendMessage function may appear within except clause
                self.alert_pipe.send(message)
                self.alert_pipe_semaphore.set()
            except Exception as err:
                l_err = 'sendAlert failed: %s' % err
                self.logger.error(l_err)
                self.errors.append(l_err)
            
    def stop(self):
        """Stops module"""
        self.status = 'Stopping'
        self.logger.debug('Stopping')
        self.isWorking = False
    
    
    #Functions to be overwritten in child classes
    #This function runs on every turn and should represent all current operations for module
    def process(self):
        """The function runs every cycle from run()

        You should override it to add module-specific features
        """
        return
        