#!/usr/bin/python3
"""Base for messengers"""
VERSION = '1.2.7'
#Interface class for all qbot connectors.
import os
import threading
import queue
import logging
from datetime import datetime
from time import sleep

class QMessenger(threading.Thread):
    """Defines basic behaviour of a messenger module"""
    def __init__(self, **config):
        """Sets messenger basic values:

        logger - copy of qbot logger. Difference is just the name
        queue - Common command queue
        MAX_MESSAGE_LENGTH - Maximum single message length. If message exeed the value it will be divided into multiple ones
        timeout - time interval between run() cycles
        savedir = default download directory
        proxies = proxies
        shortStatusText - first part of status
        getStatusText - status part representing receive commands process state (OK, errors etc)
        sendStatusText - represents send message process state
        """
        threading.Thread.__init__(self)
        self.name = "%s_%s" % (config['name'], self.name)
        self.logger = logging.getLogger(self.name)
        for h in config['logger'].handlers:
            self.logger.addHandler(h)
        self.logger.setLevel(config['logger'].level)        
        self.logger.info('Init started')
        self.queue = config['queue']
        self.isWorking=True
        self.MAX_MESSAGE_LENGTH = config['MAX_MESSAGE_LENGTH'] if 'MAX_MESSAGE_LENGTH' in config.keys() else 4096
        self.timeout = config['timeout'] if 'timeout' in config.keys() else 1
        self.savedir = config['save_directory'] if 'save_directory' in config.keys() else 'download'
        self.proxies = config['proxies'] if 'proxies' in config.keys() else None
        self.isConnected = False
        self.shortStatusText = '%s version %s: ' % (self.name, config['VERSION']) if 'VERSION' in config.keys() else '%s version %s: ' % (self.name, VERSION)
        self.getStatusText = 'OK'
        self.sendStatusText = 'OK'
        self.statusText = '%s\n%s\n%s' % (self.shortStatusText, self.getStatusText, self.sendStatusText)
        #self.logger.info('Init completed')

    def run(self):
        """Main function"""
        self.logger.info('Running')
        while self.isWorking:
            sleep(self.timeout)
            self.statusText = '%s\ngetMessages %s\nsendMessage %s' % (self.shortStatusText, self.getStatusText, self.sendStatusText)
            #Processing incoming messages
            try: #Processing status of connector
                res = self.getMessages()
                if not res['ok']:
                    if self.isConnected:
                        msg = 'error: %s' % (res['status'])
                        self.logger.error(msg)
                        self.isConnected = False
                        self.getStatusText = msg
                    continue
##                self.logger.debug(res)
                messages = res['messages']
                if not self.isConnected:                
                    #self.logger.debug('Result: {}'.format(res))
                    self.getStatusText = 'OK: %s' % res['status']
                    self.isConnected = True
                total_updates = len(messages)
            except Exception as err:
                msg = "failed: %s" % err
                self.logger.debug(msg)
                if self.isConnected:
                    self.logger.error(msg)
                    self.getStatusText = msg
                    self.isConnected = False
                total_updates = 0
            if total_updates == 0:
                continue
            for message in messages:
                if message == None:
                    continue
                self.logger.debug("New message from '%s': text='%s', id=%s, replyto=%s" %(message['user_id'], message['text'], message['message_id'], message['replyto']))
                if len(message['files']) > 0:
                    command = 'File'
                    if not message['text']:
                        command += ' %s' % message['text']
                    if not message['caption']:
                        command += ' %s' % message['caption']
                else:
                    try:
                        command = message['text']
                    except Exception as err:
                        command = "Unknown: %s" % err
                        self.logger.error("Message has no text: %s" %err)
                command = command.strip()
                #self.logger.debug("New command:text='%s', from=%s, date=%s, files: %d" % (command, message['message']['from']['username'], str(datetime.fromtimestamp(message['message']['date'])), len(files)))
                queueCommand = {'self' : self, 'command' : command, 'user_id' : message['user_id'], 'message_id' : message['message_id'],\
                                'message_time' : message['message_time'], 'replyto': message['replyto'], 'files': message['files'], 'message' : message['message']}
                if command.upper() == 'TEST': #for 'ping connector' purposes. So we can check state of connector even without working service
                    self.reply(msg=self.statusText, originalCommand=queueCommand)
                self.queue.put(queueCommand)
        #On exit write to log
        self.logger.debug('Exit')

    def getFiles(self, files, path=None):
        """Downloads requested files"""
        res = ''
        if not path:
            path = self.savedir
        for f in files:
            self.logger.debug('File: %s' % f)
            res += self.get_file(f, path) + '\n'
        return res

    #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #The fuctions below need to be overwritten in child classes

    def getMessages(self):
        """Reads user messages (commands). Messenger-specific function. Should be overrided in derived classes
        
        Should return dict() with to keys: 'ok' (boolean) and messages( list())
        every message of list if present should include
            'text':NoneDefault, 'caption':NoneDefault, 'files':[], 'message_id': NotNull,
            'user_id':NotNull, 'message_time':NotNull, 'replyto':NotNull, 'message':original_message}
        files = list(). Should contain if present at least 'file_name', 'file_id', 'file_type'
        """

        #return value = {'ok' : Boolean, 'messages' : list(
                                                        # {'text':NoneDefault, 'caption':NoneDefault, 'files':[]Default, 'message_id': NotNull,
                                                        # 'user_id':NotNull, 'message_time':NotNull, 'replyto':NotNull, 'message':original_message}
                                                        #)
        res = {'ok': False, 'messages': []}
        return res

        
    def sendMessage(self, msg, to):
        """Sends msg to to. Should be overrided"""
        res = "Empty function sendMessage() needs to be overwritten in child classes"
        logger.error(res)
        self.sendStatusText = res
        return res
    
    def reply(self, msg, originalCommand):
        """Sends msg to originalCommand['replyto']"""
        return self.sendMessage(msg, originalCommand['replyto'])
    
    def sendFile(self, to, fileName):
        """Sends file 'fileName' to 'to'. Should be overrided"""
        res = "Empty function sendFile() needs to be overwritten in child classes"
        logger.error(res)
        return res

    def get_file(self, file, path=None):
        """Gets 'file' from messenger. Should be overrided"""
        if not path:
            path = self.savedir
        fname = "%s/%s" %(os.path.normpath(self.savedir), file[type]['title'])
        res = '%s - error: %s' % (fname, "Not implemented in parent class")
        self.logger.error(res)
        return res
    
    #Stop daemon
    def stop(self):
        """Stops messenger"""
        self.logger.debug('Stopping')
        self.isWorking = False    
