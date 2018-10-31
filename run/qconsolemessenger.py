#!/usr/bin/python3
VERSION = '1.2.7'

import socket
from datetime import datetime
from qmessenger import QMessenger

class QConsoleMessenger(QMessenger):
    def __init__(self, **config):
        QMessenger.__init__(self, VERSION=VERSION, **config)
        self.sock = socket.socket()
        self.port = config['port']
        if 'sockBufferSize' in config.keys():
            self.sockBufferSize = config['sockBufferSize']
        else:
            self.sockBufferSize = 1024
        if 'timeout' in config.keys():
            self.timeout = config['timeout']
        else:
            self.timeout = 0    
        self.logger.debug('Console socket created: %s' % self.sock)
        self.message_id=0
        self.unbinded = True
        self.bind_socket()
        if self.unbinded:
            raise Exception(self.getStatusText)
        self.addr = (None,None)
        self.user_id = 'Telnet'
        self.logger.info('Init completed')

    def bind_socket(self):
        if self.unbinded:
            self.sendStatusText = 'Unbinded'
            self.getStatusText = self.sendStatusText
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind(('', self.port))
                self.unbinded = False
                self.sendStatusText = 'Binded: %s' % self.sock
                self.getStatusText = self.sendStatusText
                self.logger.debug(self.sendStatusText)
            except Exception as err:
                self.sendStatusText = 'Bind failed: %s' % err
                self.getStatusText = self.sendStatusText
                self.logger.error(self.sendStatusText)
                self.isWorking = False
                
    def getMessages(self):
        res = {'ok': False, 'messages':[], 'status':'Client lost: %s:%s' % (self.addr[0], self.addr[1])}
        try:
            self.isClosed = self.conn._closed
        except Exception:
            self.isClosed = True
        if self.isClosed:
            self.getStatusText = 'Client lost: %s:%s' % (self.addr[0], self.addr[1])
            self.sendStatusText = self.getStatusText
            self.logger.info(self.getStatusText)
            self.isConnected = False
            self.sock.listen(1)   
            try:
                self.conn, self.addr = self.sock.accept()
                r = 'Connected %s:%s' % (self.addr[0], self.addr[1])
                self.logger.debug(r)
                res['status'] = r
                res['ok'] = True
            except Exception as err:
                r = 'Connect failed: %s' % err
                res['status'] = r
                res['ok'] = False
                self.logger.error(r)
                return res
        message = self.conn.recv(self.sockBufferSize).rstrip().decode()
        res['ok'] = True
        res['status'] = 'OK'
        if not message:
            return res
        self.logger.debug('Message received: %s' % message)
        if message == 'quit':
            r = 'Client lost: %s:%s' % (self.addr[0], self.addr[1])
            res['status'] = r
            res['ok'] = False
            self.logger.debug(r)
            #self.isWorking = False
            self.conn.close()
            return res
        self.message_id += 1
        msg = {'text' : message, 'caption': None, 'user_id' : self.user_id, 'message_id' : self.message_id,\
                'message_time' : str(datetime.now()).split(".")[0], 'replyto':"%s:%s" %(str(self.addr[0]), str(self.addr[1])), 'files': [], 'message' : message}
        res['messages'].append(msg)
        return res
    
    def reply(self, msg, originalCommand):
        self.sendMessage(msg)
    #Unexpectadly, sends the message from Telegram bot
    def sendMessage(self, msg, to=None):
        try:
            self.logger.debug("Sending message '%s'..." % (msg.splitlines()[0]))
            self.conn.send(msg.encode() + b'\r\n')
            res = 'OK'
        except Exception as err:
            res = "failed: %s" % err
        self.sendStatusText = res
        self.logger.error(res)
        return res

    def stop(self):
        QMessenger.stop(self)
        self.sock.shutdown(socket.SHUT_RDWR)
