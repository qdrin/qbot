#!/usr/bin/python3
VERSION = '1.2.6'

import requests
import socks
import os
from qmessenger import QMessenger
from datetime import datetime

class QTelegramMessenger(QMessenger):
    def __init__(self, **config):
        QMessenger.__init__(self, **config, VERSION=VERSION)
        self.url = config['url']
        self.file_url = self.url.replace('api.telegram.org/','api.telegram.org/file/')
        if 'file_types' in config.keys():
            self.file_types = config['file_types']
        else:
            self.file_types = ['photo', 'document', 'audio']
        self.logger.info('Init completed')


##    def run(self):
##        QMessenger.run(self)
    
    def getMessages(self):
        res = {'ok':False, 'messages':[], 'status': 'Not connected'}
        #return res # just for debug
        resp = self.get_updates(self.url)
        update_id = None
        res['ok'] = resp['ok']
        if not res['ok']:
            return res
        res['status'] = 'Not OK'
        msgCount = len(resp['result'])
        if msgCount > 0:
            update_id = resp['result'][msgCount-1]['update_id']
            self.logger.debug("%d messages, last update_id=%d" % (msgCount, update_id))
        for r in resp['result']:
            text, caption = None, None
            files = []
            
            if 'text' in r['message'].keys():
                text = r['message']['text']
            if 'caption' in r['message'].keys():
                caption = r['message']['caption']
            file_keys = list(filter(lambda x: x in self.file_types, r['message'].keys()))
            for fk in file_keys:
                #type of files should be list()
                if type(r['message'][fk]) == type({}):
                    files.append(r['message'][fk])
                else:
                    files += r['message'][fk]
                for file in files:
                    if not 'file_name' in file.keys():
                        file['file_name'] = file['file_id']
                self.logger.debug([f['file_name'] for f in files])
            msg = {'text': text, 'caption': caption, 'files': files, 'user_id': r['message']['from']['id'], 'message_id': r['message']['message_id'],\
                   'message_time': str(datetime.fromtimestamp(r['message']['date'])), 'replyto': r['message']['chat']['id'], 'message':r}
            res['messages'].append(msg)
        #Shift start update_id for next request
        if update_id:
            resp = self.get_updates(self.url, update_id + 1)
        res['status'] = 'OK'
        return res
    
    #Gets updates for Telegram conversation. Inner use only.
    def get_updates(self, request, offset=0):
        if offset > 0:
            params = {'offset': offset}
        else:
            params = ''
        response = requests.get(request + "getUpdates", data = params, proxies=self.proxies)
        return response.json()

    #Unexpectadly, sends the message from Telegram bot
    def sendMessage(self, msg, to):
        i = 0
        params = {'chat_id': to}
        self.sendStatusText = 'OK'
        try:
            while i <= len(msg):
                j = i+self.MAX_MESSAGE_LENGTH if i+self.MAX_MESSAGE_LENGTH <= len(msg) else len(msg)
                params['text'] = msg[i:j]
                response = requests.post(self.url + 'sendMessage', data=params, proxies = self.proxies)
                i += self.MAX_MESSAGE_LENGTH
        except Exception as err:
            self.sendStatusText = "Send message failed: %s" % (err)
            self.logger.error(self.sendStatusText)        
        self.sendStatusText = 'sendMessage - %s' % response
        self.logger.debug(self.sendStatusText)
            
    
    def reply(self, msg, originalCommand):
        return self.sendMessage(msg, originalCommand['message']['message']['chat']['id'])
    
    
    def sendFile(self, to, fileName):
        if not os.path.exists(fileName):
            res = "%s doesn't exist" % fileName
            self.logger.debug(res)
            return res
        
        params = {'chat_id':to}
        files = {'document': open(fileName, 'rb')}
        try:
            resp = requests.post(self.url+'sendDocument', files=files, data=params, proxies=self.proxies)
            if resp.ok:
                res = resp.json()
            else:
                res = "sendFile failed: %s" % resp.reason
            self.logger.debug(res)
        except Exception as err:
            res = 'sendFile failed: %s' % err
            self.logger.error(res)
            self.sendStatusText = res        
        return res
    
    #file is native variable message['file']
    def get_file(self, file, path = None):
        if not path:
            path = self.savedir
        self.logger.debug(file)
        file_content = None
        sz0 = file['file_size']
        #Photos don't have file_name key
        fileFullName = "%s/%s" %(path, file['file_name'])
        resp = requests.get(self.url+'getFile', data={'file_id':file['file_id']}, proxies=self.proxies)
        if resp.ok:
            file_path = resp.json()['result']['file_path']
            res = requests.get(self.file_url+file_path, proxies=self.proxies)
            sz = 0
            if res.status_code == 200:
                fil = open(fileFullName, 'wb')
                sz = fil.write(res.content)
                resStr = '%s: %d/%d bytes' % (fileFullName, sz, sz0)
            else:
                resStr = '%s - error: %s' % (fileFullName, resp.json())
        else:
            resStr = '%s - error: %s' % (fileFullName, resp.json())
        return resStr
    
    
    def stop(self):
        self.logger.debug('Stopping')
        self.isWorking = False
