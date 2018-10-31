VERSION = '1.2.7'

import vk_api
import threading
import os
import requests
from datetime import datetime
from time import sleep
from vk_api.longpoll import VkLongPoll, VkEventType
from qmessenger import QMessenger

class QVkMessenger(QMessenger):
    """VC (vc.com) connector for qbot"""
    MAX_MESSAGE_LENGTH = 4096
    MAX_MESSAGE_LENGTH_FOR_LOG = 80
    def __init__(self, **config):
        QMessenger.__init__(self, VERSION=VERSION, **config)
        self.dvd_group_id = config['group_id']
        self.group_token = config['group_token']
        self.vk_session = vk_api.VkApi(token = self.group_token)
        self.vk = self.vk_session.get_api()
        self.vk_user = vk_api.VkApi(self.vk_session)
        self.lPoll = VkLongPoll(self.vk_session)
        self.errorTimeout = 5
        self.logger.debug('Init completed')

    def getMessages(self):
        events = self.lPoll.check()
        res = {'ok':True, 'messages': [], 'status': 'OK'}
        
        for event in events:
            #self.logger.debug("New event: type=%s, user_id=%s,text=%s,to_me='%s', from_me='%s', Attachments: %s" % (event.type, event.user_id, event.text, event.to_me, event.from_me, event.attachments))
            if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                self.logger.debug("New event: type=%s, user_id=%s,text=%s,to_me='%s', from_me='%s', Attachments: %s" % (event.type, event.user_id, event.text, event.to_me, event.from_me, event.attachments))
                files = []
                caption = None    
                try:
                    text = event.text
                except Exception as err:
                    self.logger.warning('Read message text failed: %s' % err)
                    text = None
                if len(event.attachments) > 0:
                    msg = self.vk.messages.getById(message_ids=event.message_id)
                    atch_list = msg['items'][0]['attachments']
                    for f in atch_list:
                        type = f['type']
                        url = f[type]['url']
                        files.append({'file_name':f[type]['title'],'file_size':f[type]['size'], 'file_id':f[type]['id'], 'file_type':type, 'url':url})
                message = {'text': text, 'caption': caption, 'files': files, 'user_id': event.user_id, 'message_id': str(event.message_id),\
                       'message_time': str(event.datetime), 'replyto': event.user_id, 'message':event}
                res['messages'].append(message)
        res['status'] = 'OK: %s messages' % len(res['messages'])
        return res

    def get_file(self, file, path=None):
        if not path:
            path = self.savedir
        fname = "%s/%s" %(os.path.normpath(path), file['file_name'])
        resp = requests.get(file['url'])
        if resp.ok:
            fil = open(fname, 'wb')
            sz = fil.write(resp.content)
            fil.close()
            res = "%s: %s/%s bytes" % (fname, sz, file['file_size'])
            self.logger.debug(res)
        else:
            res = '%s - error: %s' % (fname, resp.json())
            self.logger.error(res)
        return res
        
    def reply(self, msg, originalCommand):
        return self.sendMessage(msg, originalCommand['user_id'])
        
    def sendMessage(self, msg, to):
        i = 0
        self.sendStatusText = 'OK'
        try:
            while i <= len(msg):
                j = i+self.MAX_MESSAGE_LENGTH if i+self.MAX_MESSAGE_LENGTH <= len(msg) else len(msg)
                self.vk.messages.send(
                    user_id=to,
                    message=msg[i:j])
                i += self.MAX_MESSAGE_LENGTH
        except Exception as err:
            self.sendStatusText = "Send message failed: %s" % (err)
            self.logger.error(self.sendStatusText)
        self.logger.debug('Message sent: %s' % (msg[0:self.MAX_MESSAGE_LENGTH_FOR_LOG]))
       