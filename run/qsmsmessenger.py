#!/usr/bin/python3
VERSION = '1.2.7'

import os
import threading
import socket
import queue
import logging
from datetime import datetime
from time import sleep
#Module pure-python-adb
from adbe import adbe
from qsmsdecoder import decodeSMS
from qsmsdecoder import encodeSMS
from qsmsdecoder import decodeGSM
from qsmsdecoder import encodeGSM
from qmessenger import QMessenger
from qsmsdecoder import catSMS
import binascii

MAX_MESSAGE_LENGTH = 70
MAX_SEQUENCED_MESSAGE_LENGTH = 67


class QSMSMessenger(QMessenger):
    def __init__(self, **config):
        QMessenger.__init__(self, VERSION=VERSION, **config)
        self.devSerial = config['device_serial']
        self.modemBusy = False #flag to share modem with get and send processes
        self.waitForConnect = 30 #Timeout between connection attempts
        if 'long_message_wait' in config.keys():
            self.longMessageWaitingTimeout = config['long_message_wait']
        else:
            self.longMessageWaitingTimeout = 5 #seconds for multi-part message waiting
        self.l_messages = list() #Long SMS store
        self.sequence = 1 #Sequence number for long messages
        #self.modemSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.messageBoxes={'IN_UNREAD':0, 'IN_READ':1, 'ST_UNSENT':2, 'ST_SENT':3,'ALL':4}
        self.isConnected = self.initModem()
        self.clearMessages()
        self.logger.info('Init completed')

    
    def initModem(self):
        #self.logger.debug("Connecting modem")
        try:
            res = adbe.execute_adb_command("connect %s" % self.devSerial)
            self.logger.debug(res)
            if not 'connected' in res:
                self.isConnected = False
                res = 'Modem not connected'
                self.getStatusText = res
                self.sendStatusText = res
                self.isConnected = False
                return False
        except Exception as err:
            res = 'ADB connect failed: %s' % err
            self.logger.error(res)
            self.getStatusText = res
            self.sendStatusText = res
            self.isConnected = False
            return False
        try:
            i = self.sendAT("at+cmgf=0").index('OK')
            res = 'OK'
            #i = self.sendAT("at+cscs=\"UCS2\"").index('OK')
            self.isConnected = True
            res = 'Modem connected'
            self.logger.debug(res)
        except Exception as err:
            res = "AT command failed: %s" % (err)
            self.logger.error(res)
            self.isConnected = False
        self.getStatusText = res
        self.sendStatusText = res
        return self.isConnected
    
    #Senging commands to modem
    def sendAT(self, atCmd):
        t0 = datetime.now()
        atString = "atc '%s'" % atCmd
        res = 'ERROR %s' % atCmd
        while self.modemBusy and (datetime.now() - t0).seconds < self.timeout:
            sleep(self.timeout/10)
        if self.modemBusy:
            self.isConnected = False
            self.logger.error('Modem is busy')
        self.modemBusy = True
        try:
            srcres = adbe.execute_adb_shell_command(atString).splitlines()
            res = list(filter(self.filterModemOutput,srcres))
        except Exception as err:
            res = "%s: %s" % (atCmd, err)
            self.logger.error(res)
        self.modemBusy = False
        #self.logger.debug(res)
        return res

    def filterModemOutput(self,r):
        #self.logger.debug("Applying filter to: '%s'" % r)
        if r.strip() and r.find('Waiting') == -1:
            return True
        else:
            return False
    
    #Gets messages from  folder
    def getMessages(self, mBox=None):
        res = {'ok': False, 'messages': [], 'status': 'Modem disconnected'}
        if not 'OK' in self.sendAT('AT'):
            if not self.initModem():
                sleep(self.waitForConnect)
                return res
        res = {'ok': True, 'messages': [], 'status': 'OK'}
        if not mBox:
            mBox = 0
        atCommand = "at+cmgl=%d" % mBox
        atres = self.sendAT(atCommand)
        messages=[]
        
        #parse modem response, searching for 'CMGL: strings that contain message data
        for i in atres:
            if i.find("CMGL:") != -1:
                s=i.replace("+CMGL: ", "")
                s=s.split(",")
                fld=s[1]
                msgId=int(s[0])
                msgLen=int(s[3])
                msgUtf16 = atres[atres.index(i)+1]
                self.logger.debug('In SMS[%s]: %s' % (i, msgUtf16))
                msg = decodeSMS(msgUtf16)
                self.deleteMessage(msgId)
                #adding modem data
                msg['message_id'] = msgId
                msg['folder_id']=fld
                msg['message_length']=msgLen
                msg['timereceived']=datetime.now()

                #self.logger.debug(msg) # for testing only
                if msg['is_long']: #Sorting messages for long/simple
                    ieds = msg['ieds'][0]
                    self.logger.debug("Long SMS received. ID=%d. Sequence %d/%d" % (msgId, ieds['ied3'], ieds['ied2']))
                    self.l_messages.append(msg)
                else:
                    if msg['dcs'] == 8: #means UCS2
                        text = binascii.unhexlify(msg['ud']).decode('utf-16-be')
                    else: #means 0 that is 7-bit GSM encoding
                        text = decodeGSM(msg['ud'])
                    msg['text'] = text
                    message = {'text': text, 'message_id': msgId, 'caption': None, 'files': [], 'message_time':msg['time'],\
                               'replyto': msg['msisdn'], 'user_id': msg['msisdn'], 'message': msg}
                    messages.append(message)
            
        #working with long messages only
        #print(res)
        if self.l_messages:
            self.logger.debug("Long messages to work: %d" % len(self.l_messages))
            lres = catSMS(self.l_messages)
            #self.logger.debug("Long messages work status: %s" % lres['sequence_info'])
            if lres['sequence_info']['full'] or (datetime.now() - lres['mlist'][0]['timereceived']).seconds > self.longMessageWaitingTimeout:
                msg = lres['mlist'][0]
                msg['text'] = lres['text']
                message = {'text': lres['text'], 'message_id': msg['message_id'], 'caption': None, 'files': [], 'message_time':msg['time'],\
                           'replyto': msg['msisdn'], 'user_id': msg['msisdn'], 'message': msg}                
                messages.append(message)
                self.logger.debug('Sequence accomplished: %s' % lres['sequence_info'])
            else:
                self.logger.debug('Wait for messages: %s' % lres['sequence_info'])
                for m in lres['mlist']:
                    self.l_messages.append(m)
                self.logger.debug("Long messages to work: %d" % len(self.l_messages))
            self.logger.debug("Long messages remains: %d" % len(self.l_messages))
        res['messages'] = messages
        #print(res)
        return res
    
    def deleteMessage(self, msgId):
        atCommand = "at+cmgd=%s" % msgId
        res = self.sendAT(atCommand)
        self.logger.debug("Deleting message %s: %s" % (msgId, res))
        return res
    #Unexpectadly, sends the message from Telegram bot
    
    def clearMessages(self):
        res = self.getMessages(4)
        for m in res['messages']:
            self.deleteMessage(m['message_id'])
        
    def reply(self, msg, originalCommand):
        return self.sendMessage(msg, originalCommand['message']['msisdn'])
        
    def sendMessage(self, msg, to):
        #addr = msisdn
        self.sendStatusText = 'Not OK'
        gsm = list()
        if len(msg) > MAX_MESSAGE_LENGTH:
            ins_num = 1 #instance number
            ins_max = int(len(msg)/MAX_SEQUENCED_MESSAGE_LENGTH) # max instances
            if len(msg) % MAX_SEQUENCED_MESSAGE_LENGTH > 0:
                ins_max += 1
            self.logger.debug("Forming long message. Parts: %d" % ins_max)
            for i in range(0, len(msg), MAX_SEQUENCED_MESSAGE_LENGTH):
                m=msg[i: i + MAX_SEQUENCED_MESSAGE_LENGTH]
                gsm.append(encodeSMS(to, m, ins_num, ins_max, self.sequence))
                ins_num += 1
            if self.sequence < 255: #change sequence number for future
                self.sequence += 1
            else:
                self.sequence = 1
        else:
            gsm.append(encodeSMS(to, msg))
        self.logger.debug("%d messages ready" % len(gsm))
        for g in gsm:
            gsm_msg = g['message']
            gsm_len = g['message_length']
            atCmd = "at+cmgs=%d\x0D%s\x1a" % (gsm_len, gsm_msg)
            self.logger.debug("Send GSM:'%s'(length=%d)" % (g['message'], g['message_length']))
            res = self.sendAT(atCmd)
            self.sendStatusText = "send: %s" % res
            self.logger.debug(res)
#        self.logger.debug("Message sent: '%s'. Response: '%s'" % (msg, response))

    def stop(self):
        self.logger.debug('Stopping')
        self.isWorking = False
