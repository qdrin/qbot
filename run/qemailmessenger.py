#!/usr/bin/python3
VERSION = '1.2.7'
"""Email connector for qbot"""
import os
from qmessenger import QMessenger
import email
import smtplib
import imaplib
from dateutil import parser
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.utils import COMMASPACE, formatdate

class QEmailMessenger(QMessenger):
    def __init__(self, **config):
        QMessenger.__init__(self, VERSION=VERSION, **config)
        self.isOk = True
        self.mailServer = config['imap_server']
        self.smtpServer = config['smtp_server']
        self.mailPort = config['imap_port']
        self.login = config['login']
        self.password = config['password']
        self.mailFolder = config['mail_folder']
        self.searchSubject = [config['search_subject'], 'Re: %s' % config['search_subject']]
        self.isWorking = True
        self.smtpConnection = None
        self.imapConnection = None
        self.smtpConnection = self.establishSmtpConnection()
        self.imapConnection = self.establishImapConnection()
        self.selectFirstLineOnly = True
        self.logger.info('Init completed')
        

    def simpleSendMessage(self, fromaddr, toaddr, subj, text, fileName=None):
        connection = self.establishSmtpConnection()
        if connection:
            body = '\r\n'.join((
                'From: %s' % fromaddr,
                'To: %s' % toaddr,
                'Subject: %s' % subj,
                '',
                text))
            msg = MIMEText(text, 'plain', 'utf-8')
            message = MIMEMultipart()
            message['Subject'] = subj
            message['From'] = fromaddr
            message['To'] = toaddr
            message['Return-path'] = fromaddr
            message['Date'] = formatdate(localtime=True)
            message.attach(msg)
            if fileName:
                fil = open(fileName, 'rb')
                atch = MIMEApplication(fil.read(), Name=os.path.basename(fileName))
                fil.close()
                atch['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(fileName)
                message.attach(atch)
            self.logger.debug('Sending From: "%s", To: "%s", Subject: "%s"' %(fromaddr, toaddr, subj))
            try:
                connection.sendmail(fromaddr, toaddr, message.as_string())
            except Exception as err:
                res = "Send error: %s" % (err)
                self.sendStatusText = res
                self.logger.error(res)
                return res
            res = 'OK'
            if fileName:
                res += '\n%s' % fileName
            self.logger.debug(res)
            self.sendStatusText = res
        else:
            res = "Connection lost"
            self.sendStatusText = res
            self.logger.error(res)
        return res
            
    def reply(self, msg, originalCommand):
        a = originalCommand['message']
        fromaddr = a.get('To')
        toaddr = a.get('From')
        subj = a.get('Subject')
        enc = a.get('Content-Transfer-Encoding')
        if not subj.upper().startswith('RE:'):
            subj = 'Re: ' + subj
        return self.simpleSendMessage(fromaddr, toaddr, subj, msg)

    #Just for connectivity
    def sendMessage(self, msg, to, fileName=None):
        fromaddr = self.login
        subj = "%s: send" % self.searchSubject[0]
        return self.simpleSendMessage(fromaddr, to, subj, msg, fileName=fileName)
        
    def sendFile(self, to, fileName):
        self.logger.debug(to)
        self.logger.debug(fileName)
        self.sendMessage(fileName, to, fileName = fileName)
        return False
    
    def get_message(self, id, connection = None):
        if not connection:
            connection = self.establishImapConnection()
        if not connection:
            return None
        st, res = connection.fetch(id, 'RFC822')
        msg = res[0][1]
        message = email.message_from_bytes(msg, _class=email.message.EmailMessage)
        return message
    
    def getMessages(self):
        ret_res = {'ok': False, 'messages': [], 'status': ''}
        connection = self.establishImapConnection()
        if connection:
            connection.select(self.mailFolder)
            status, res = connection.search(self.searchSubject[0], 'unseen')
            if status != 'OK':
                op_res = "IMAP failed: %s" % (res[0])
                ret_res['status'] = op_res
                self.logger.warning(op_res)
                return res
            ret_res['ok'] = True
            ret_res['status'] = "OK"
            if len(res[0]) == 0:
                return ret_res
            msg_ids = res[0].decode('UTF-8').split()
            self.logger.debug('Found %d message(s). Id(s): %s' % (len(msg_ids), res[0].decode('UTF-8')))
            self.messages = list()
            for id in msg_ids:
                message = self.get_message(id, connection)
                subject = message.get('subject')
                sender = None
                #First search simple sender SMTP address
                sender = list(filter(lambda x: x.startswith("smtp.mailfrom"), message['Authentication-Results'].split()))[0].split('=')[1]
                if not sender: #If not found, get full From field with any added information
                    sender = message.get('From')
                msg_id = message.get('Message-ID')
                msg_date = str(parser.parse(message.get('Date')))
                self.logger.debug('Content type="%s"' % message['Content-Type'])
                files = []
                if message['Content-Type'].startswith('text/plain'):
                    body_bytes = message.get_payload(decode=True)
                    body = body_bytes.decode('UTF-8')
                else:
                    mmsg = message.get_payload()[0]
                    body = mmsg.get_payload(decode=True).decode().replace('\r', '')
                    attachments = list(message.iter_attachments())
                    for a in attachments:
                        #Here we should pick the attachments
                        #self.logger.debug(part.get_content_type())
                        fName = a.get_filename()
                        if not fName:
                                continue
                        files.append({'file_name': fName, 'file_id': id, 'file_type':a.get_content_type(), 'attachment':a})
                        self.logger.debug('file (%s): %s' % (a.get_content_type(), fName))
                
                self.logger.debug('Body starts with: "%s"' % body.splitlines()[0])
                if self.selectFirstLineOnly:
                    for s in body.split('\n'):
                        if len(s.strip(' \t')) > 0:
                            body = s
                            break
                self.logger.debug('Message received from "%s": Subject="%s", Text="%s", Date=%s, %d attachments' % (sender, subject, body, msg_date, len(files)))
                a = {'text':body, 'caption': None, 'user_id':sender, 'message_id':msg_id, 'message_time':msg_date, 'files':files, 'replyto': sender, 'message':message}
                ret_res['messages'].append(a)
            ret_res['ok'] = True
        else:
            op_res = 'Connection lost'
            self.logger.debug(op_res)
            ret_res['ok'] = False
            ret_res['status'] = op_res
            try:
                connection.logout()
            except Exception as err:
                connection = None
        return ret_res
    
    def deleteMessage(self, messageId):
        connection = self.establishImapConnection()
        if connection:
            connection.store(messageId, '+FLAGS', '(\\Deleted)')
            connection.expunge()
    
    def get_file(self, file, path=None):
        if not path:
            path = self.savedir  
        fileName = os.path.join(path, file['file_name'])
        fp = open(fileName, 'wb')
        sz = fp.write(file['attachment'].get_payload(decode=1))
        fp.close()
        res = "%s: %s bytes" % (fileName, sz)
        return res
    
    def establishImapConnection(self):
        if self.imapConnection:
            try:
                st, noopres = self.imapConnection.noop()
                if noopres[0]:
                    noopres = noopres[0].decode()
                else:
                    noopres = '?'
                if(st == 'OK'):
                    return self.imapConnection
                else:
                    self.logger.warning('NOOP failed: [%s], [%s]' % st, noopres)
            except Exception as err:
                self.logger.warning('IMAP Noop failed: "%s". Conn state: %s' % (err, self.imapConnection.state))
        try:
            connection = imaplib.IMAP4(host=self.mailServer, port=self.mailPort)
            r = connection.starttls()
            r = connection.login(self.login, self.password)
            r = connection.select(self.mailFolder)
        except Exception as err:
            self.logger.debug('IMAP connection could not be established: %s' % (err))
            self.imapConnection = None
            self.isImapConnected = False
            return None
        self.logger.debug('IMAP connection established. Server="%s", user="%s"' % (self.mailServer, self.login))
        self.imapConnection = connection
        return connection
    
    def establishSmtpConnection(self):
        if self.smtpConnection:
            try:
                st, noopres = self.smtpConnection.noop()
                noopres = noopres.decode()   
                if not noopres or len(noopres) == 0:
                    noopres = '?'
                if(st == 250):
                    return self.smtpConnection
                else:
                    self.logger.warning('SMTP NOOP failed: [%s], [%s]' % (st, noopres))
            except Exception as err:
                self.logger.warning('Connection to SMTP server lost, NOOP failed: %s' % err)        
        try:
            sconnection = smtplib.SMTP(self.smtpServer)
            r = sconnection.starttls()
            r = sconnection.login(self.login, self.password)
        except Exception as err:
            self.logger.error('Could not establish SMTP connection: %s' % (err))
            self.smtpConnection = None
            return None
        self.logger.debug('SMTP connection established. Server="%s", user="%s"' % (self.smtpServer, self.login))
        return sconnection

    def stop(self):
        self.logger.debug('Stopping')
        self.timeout = 0
        self.isWorking = False
