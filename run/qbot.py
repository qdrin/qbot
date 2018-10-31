#!/usr/bin/env python3
"""Main module. Runs as systemd service

Basic terms:
Connectors
    - additional modules each adding functionality of some messenger
    - base module - qmessenger (based on threading.Thread), base class - QMessenger
    - methods to override: getMessages(), sendMessage(), sendFile()
Manager modules
    - modules adding any desired functionality, commands and alerts
    - base module - qbasemanager (based on multiprocessing.Process), base class - QBaseManager
    - methods to override: process()
Commands - strings described in conf-files (main or module's) that
    Commands definition fields:
        commandtext: user text. Command processor parse the commands and choose the longest start match from the user-text. The rest of user-string is assumed as command parameter
        commandline: real python3 command to be execute in exec("response = 'commandline'") statement. Should return string

Need files: qbot.conf (or qbot_test.conf if isTest file exists) - configuration
            qmessenger.py - base module for connectors
            qbasemanager.py - base module for manager modules
            Other modules with classed derived from qmessenger and qbase messenger



"""

VERSION = '1.3.8'

#Check existance and validity of modules
try:
    import sys, os
    import psutil
    import signal
    import tarfile
    from time import sleep
    from queue import Queue
    import daemon
    import datetime
    import logging
    import yaml
    import json
    from multiprocessing import Pipe, Event
    import this
except Exception as err:
    print('Error! Could not import modules: %s' % err)
    sys.exit(-1)
    
#This value should be in DB COMMANDS as substitution of command arguments
PARAM_STRING='COMMAND_PARAMETERS'


class Loader(yaml.SafeLoader):
    """Adds the !include statement to yaml"""
    def __init__(self, stream):
        self._root = os.path.split(stream.name)[0]
        super(Loader, self).__init__(stream)
    def include(self, node):
        filename = os.path.join(self._root, self.construct_scalar(node))
        with open(filename, 'r') as f:
            return yaml.load(f, Loader)
Loader.add_constructor('!include', Loader.include)

def zen(some):
    """Command Дзен implementation. Returns encrypted or decrypted text of 'this' module"""
    def zen_plain(text):
        d = {}
        for c in (65, 97):
            for i in range(26):
                d[chr(i+c)] = chr((i+13) % 26 + c)
        return "".join([d.get(c, c) for c in text]) 
    res = this.s if some == '' else zen_plain(this.s)
    return res

#Functions checks if the user has admission to run the command.
#Developing. Now it just checks the fact that the user is in allowed users list
def isCommandAllowed(cmdObj):
    """Checks if the user has admission to run the command"""
    res = False
    uid = str(cmdObj['user_id']).lower()
    try:
        usr = list(filter(lambda x: x['user_id'] == uid, users))[0]
        logger.info('Command %s allowed for user %s' % (cmdObj['command'], usr))
        res = True
    except Exception as err:
        logger.error("User_id %s not found: %s" % (cmdObj['user_id'], err))
    return res
    
def init_connectors(queue, logger, connectors_config):
    """Forms connectors list from successfully created connectors"""
    global classes
    connectors = []
    #Create and start concerning class connectors for each connectors_config member and stores them in connectors list
    for conf in connectors_config:
        try:
            c = init_connector(queue=queue, logger=logger, **conf)
        except Exception as err:
            logger.error('Init connector %s failed: %s' % (conf['name'], err))
            continue
        if c:
            #logger.info('Connector added: %s' % c['name'])
            connectors.append(c)
        else:
            logger.error('Init connector %s failed' % conf['name'])
    return connectors

#create and init 1 connector
def init_connector(**conf):
    """Creates and run given connector
    
    Besides configuration file values conf must contain logger and queue
    returns dict with keys: name, connector, to, is_alive, default and autorestart
    if failed returns None
    
    """
    global classes
    dict_connector = None
    #setting autorestart key. We need False just for problem connectors to avoid error messages storm
    autorestart = conf['autorestart'] if ('autorestart' in conf.keys()) else True    
    try:
        conn = classes[conf['class']](**conf)
        #conn.setDaemon(True)
        conn.start()
    except Exception as err:
        logger.error("%s connector is not available: %s" % (conf['name'], err))
        conn = None
    if conn:
        to_list = list(filter(lambda x: x['channel'] == conf['class'], contacts))
        conn_default = True if ('default' in conf.keys() and conf['default']) else False
        dict_connector = {'name':conf['name'], 'connector': conn, 'to': to_list, 'default': conn_default, 'class':conf['class'], 'is_alive':conn.is_alive(), 'autorestart':autorestart}
    return dict_connector

def stop_manager(man_name):
    """Stops manager module with given name"""
    global managers
    mlist = list(filter(lambda x: x['name'].lower() == man_name.lower(), managers))
    m = mlist[0] if len(mlist) else None
    if m:
        logger.debug('Stopping %s' % man_name)
        m['command_pipe'].send('self.stop()')
        m['command_pipe_semaphore'].set()
        m['connector'].join(25)
        res = 'stopped'
        if m['connector'].is_alive(): #if correct stop operation failed terminating roughly
            m.terminate()
            res = 'terminated'
        res = '%s: %s' % (man_name, res)
        logger.debug(res)
        managers.remove(m)
    else:
        res = '%s: not found' % man_name
    return res
    
    
def init_manager(**conf):
    """Create and run manager module with given configuration

        Besides values from configuration file conf must contain logger value
        
    """
    global managers
    global commands
    def start_connector(**conf): #! logger must be in param list
        dict_connector = None
        command_pipe1, command_pipe2 = Pipe()
        command_evt = Event()
        alert_pipe1, alert_pipe2 = Pipe()
        alert_evt = Event()
        #Add runtime conf vars
        temp_conf = {}
        temp_conf['command_pipe'] = command_pipe2
        temp_conf['command_pipe_semaphore'] = command_evt
        temp_conf['alert_pipe'] = alert_pipe2
        temp_conf['alert_pipe_semaphore'] = alert_evt
        #setting autorestart key. We need False just for problem connectors to avoid error messages storm
        autorestart = conf['autorestart'] if ('autorestart' in conf.keys()) else True
        try:
            conn = classes[conf['class']](**conf, **temp_conf)
            #conn.daemon = True
            conn.start()
        except Exception as err:
            logger.error("%s manager is not available: %s" % (conf['name'], err))
            conn = None
        if conn:
            dict_connector = {'name':conf['name'], 'connector': conn, 'class':conf['class'], 'is_alive':conn.is_alive(), 'command_pipe': command_pipe1, \
                              'alert_pipe': alert_pipe1, 'command_pipe_semaphore': command_evt, 'alert_pipe_semaphore': alert_evt, 'autorestart': autorestart}

        return dict_connector
    if len(list(filter(lambda x: x['name'] == conf['name'], managers))): #if manager already exists
        res = '%s already running' % conf['name']
        return res
    new_man = start_connector(**conf)
    res = '%s: nothing added' % conf['name']
    if new_man:
        managers.append(new_man)
        res = '%s: started' % new_man['name']
        if 'commands' in conf.keys():
            man_commands = conf['commands'].copy()
            for cmd in man_commands:
                cmd['module'] = conf['name']
            commands.extend(man_commands)
            res = '%s (%d commands)' % (res, len(man_commands))
    return res
    
#----------------------------------------------------------------------------------------------------
#init parameters, sensors,commands, config etc.
def init():
    """Init function

    Setting global variables, runs connectors, manager modules, reading configuration files etc.
    """
    global isTest
    global connectors, managers, queue, config
    global pidFileName
    global workdir, downloaddir, uploaddir, maindir, updatefile, updatedir, backupdir
    global logger
    global commands, contacts, users, classes
    global isUpdating
    global waitForConfirm
    global startTime
    global isWorking
    global timeout
    
    isWorking = False
    timeout = 2 #Seconds to wait in every cycle    

    #if running script manually current directory is run
    if os.path.basename(os.path.realpath(os.curdir)) == 'run':
        os.chdir('..')  
    workdir = os.path.abspath(os.curdir) + '/'
    print('Working directory: %s' % workdir)
    maindir = 'run/'
    downloaddir = 'download/'
    uploaddir = 'upload/'
    backupdir = 'backup/'
    updatedir = 'update/'
    updatefile = workdir + 'update_flag'
    
    isTest, msg = (True, 'Test') if 'isTest' in os.listdir() else (False, 'Prom')  #Set True at test environment
    print('%s connectors is used' % msg)
    confFileName = maindir + 'conf/qbot.yaml' #TODO: get var from commandline
    confFileName = confFileName.replace('qbot.yaml', 'qbot_test.yaml') if isTest else confFileName
    print('Using configuration file %s' % confFileName)
    config = yaml.load(open(confFileName), Loader)
    
    logFileName = workdir + 'logqbot.txt' #TODO: get var from conf-file
    waitForConfirm = 600 #Seconds waiting for update confirm. If no approve until this time, backup system files will be restored
    startTime = datetime.datetime.now()
    isUpdating = False
    if os.path.exists(updatefile):
        isUpdating = True
        print('Updating mode - updated. Waiting for confirm %d seconds' % waitForConfirm)
    else:
        print('Updating mode - normal')
        
    print("LogFile=%s" % logFileName)
    
    #Prepare logger
    #--------------------------------------------------------------------------------------------------------
    #Prepare logger
    logger = logging.getLogger('qbot.service')
    ch = logging.StreamHandler(os.sys.stdout)
    fh = logging.FileHandler(logFileName)
    logFormat = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
    fh.setFormatter(logFormat)
    ch.setFormatter(logFormat)
    logger.addHandler(fh)
    logger.addHandler(ch)
    loglevel = getattr(logging, config['loglevel']) if ('loglevel' in config.keys()) else logging.INFO    
    logger.setLevel(loglevel)
    #--------------------------------------------------------------------------------------------------------
    
    #PID file processing
    #get PIDFilename from systemd qbot.service description
    #if PID file exists and related process is running then exit
    qbotService = open('/etc/systemd/system/qbot.service').read().splitlines()
    pidFileName = list(filter(lambda x: x.find('PIDFile') == 0, qbotService))[0].split("=")[1]
    logger.info('Using PID file %s' % pidFileName)

    if os.path.exists(pidFileName):
        try:
            pid = int(open(pidFileName).read())
        except Exception as err:
            logger.error('Can not read pid from file %s' % pidFileName)
            sys.exit(0)
        logger.warning('Pid file exists %s. Checking for process existance: %s' % (pidFileName, pid))
        if pid in psutil.pids():
            logger.warning('PID %d is running already. Could not run the second instance' % pid)
            sys.exit(0)
    pid = os.getpid() #As a daemon get our PID
    try:
        pidFile = open(pidFileName, 'w')
        pidFile.write(str(pid)) #and write it to PID-file
        pidFile.close()
        logger.debug('PID=%d has been written to %s' % (pid, pidFileName))
    except Exception as err:
        logger.error('Could not write PID=%d to PID-file: %s' % (pid, err))
        sys.exit(-1)
    #--------------------------------------------------------------------------------------------------------
    logger.removeHandler(ch)
    
    classes = {}
    #import classes from connectors and managers modules
    for class_type in ['connectors', 'managers']:
        loadings = [{'class':x['class'], 'module': x['module']} for x in config[class_type]]
        for l in loadings:
            if not l['class'] in classes.keys(): #if the class NOT already loaded -> load it
                try:
                    classes[l['class']] = __import__(l['module']).__dict__[l['class']] #The import itself
                except Exception as err:
                    l_err = "%s import failed: %s" % (l, err)
                    logger.error(l_err)
    logger.debug('%d classes imported' % len(list(classes.keys())))
    commands = {}
    #print(config['commands'])
    #Get core module commands
    commands = config['commands'].copy()
    for c in commands:
        c['module'] = __name__
    logger.info('%d commands loaded from module %s' % (len(config['commands']), __name__))
    #print(commands)
    
    contacts = config['contacts']
    logger.info('%d contacts loaded' % len(contacts))
    
    users = config['users']
    logger.info('%d users loaded' % len(users))
    
    #----------------------------------------------------------------------------------------------------------------------------------------
    queue = Queue()
    #initialize connectors
    connectors = []
    try:
        connectors = init_connectors(queue, logger, config['connectors']) #Creating and initializing all described connections
    except Exception as err:
        logger.error("Init connectors failed: %s" % (err))

    #Starting managers
    managers = []
    num_of_commands = 0
    for m in config['managers']:
        try:
            res = init_manager(logger=logger, **m)
            logger.debug(res)
        except Exception as err:
            logger.error('%s init manager failed: %s' % (m['name'], err))
    logger.info('Loaded %d managers with %d commands' % (len(managers), num_of_commands))
#--------------------------------------------------------------------------------------------------------------------------------------------
#Work functions
#--------------------------------------------------------------------------------------------------------------------------------------------
#tail of log file
def tail(fname, n):
    """Returns last lines of file"""
    lines = os.popen("tail -n %d %s" % (n, fname)).read()
    return lines

def showMessages(param = None):
    """Returns last lines of log file"""
    last = int(param) if param else 20
    res = tail(logger.handlers[0].baseFilename, last)
    return res
      
#Test function to check new functionality
def testFunction():
    """Test function. Returns just version and 'OK'"""
    res = 'Main module version %s: OK.' % VERSION
    return res

def exitFunction(signum, frame):
    """Exit"""
    logger.debug('Caught signal %s' % signum)
    global isWorking
    isWorking = False
    return('Stopping')

def runShellCommand(cmd):
    """Runs shell command
    
    if shell process doesn't exit in 10 seconds closes it
    Return read() of process output
    """
    cmdTimeout = 10 # wait 2 seconds for command exit
    t0 = datetime.datetime.now()
    logger.debug('Running shell command: %s' % cmd)
    res = ''
    p = os.popen(cmd)
    while not p._proc.poll() and (datetime.datetime.now() - t0).seconds < cmdTimeout:
        res = '%s\n%s' % (res, p.readline())
    p.close()
    logger.debug(res)
    return res

def help(topic = None):
    """Help for the available commands

    Usage: Help [module.][command]
    if no parameters provided returns usage and list of modules
    if just module part present returns list of module commands (__main__ is the 'system' module name)
    else returns the help text from config file
    """
    logger.debug('Help topic=%s' % topic)
    def manager_info(manager_name):
        return 'Доступные команды\n' + '\n'.join([x['commandtext'] for x in list(filter(lambda y: y['module'] == manager_name, commands))])
    if not topic: #Without topic return just list of modules
        man_list = [__name__]
        man_list.extend([x['name'] for x in managers])
        res = "Usage: Help '[МОДУЛЬ].[КОМАНДА]'\nПо умолчанию используется модуль '%s', он может быть пропущен(точка остается).\nДоступные модули:\n" % __name__
        res += '\n'.join(man_list)
    elif topic.endswith('.'):
        man_name = topic.rstrip('.') if len(topic) > 1 else __name__
        res = manager_info(man_name)
    else:
        cmd = getCommand(topic)
        res = cmd['command']['helptext'] if cmd['command'] else 'Command not found'
    return res

#Scans commands set for the best match (longer string matching)
#commands and modules are not case sensitive, but params are
def getCommand(cmdFull_original):
    """Finds the most suitable command for user command text

    command format: [[module].]Command Parameters
    function searches for the longest command text match
    if module is given just the manager module commands are considered (don't use dot in general command texts to avoid mistifications)
    """
    global commands
    cmdFull = cmdFull_original.strip()
    cmdLower = cmdFull.lower()
    cmd = None
    params = None
    res_len = 0
    for c in commands:
        cLower = c['commandtext'].lower()
        managerLower = c['module'].lower()
        if (cmdLower.startswith(cLower) or cmdLower.startswith('%s.%s' % (managerLower, cLower))) and len(c['commandtext']) > res_len:
            cmd = c
            res_len = len(c['commandtext'])
            cmd_index = cmdLower.find(cLower)
            params = '"%s"' % cmdFull[res_len+cmd_index:].strip() # params MUST be the string type
    res = {'command': cmd, 'params':  params}
    logger.debug(res)
    return res

#change script file(s) to newer versions
#files should be downloaded before by other methods
def update(filename = None):
    """updates 'system' files

    files should be compressed to 'tar.gz' archive with 'run' subdirectory cause the extracting is done from work directory
    Before extracting any new files all the old ones will be compressed to 'backup/run.tar.gz' archive, update_flag file created and __main__script exited
    update_flag file indicates the number of system starts after updating. If the number greater than zero, start_qbot.sh shell script should restore backup/run.tar.gz
    and run previous version of system.
    Also after succsessful after-update start system gives you 10 minutes to check and approve this update (command 'Approve update'). If no approve was given,
    the backup/run.tar.gz will be restored and system downgraded
    """
    global isWorking
    
    if os.path.exists(updatefile):
        res = "Update flag exists '%s'. Cannot run new update until the previous one not accomplished" % updatefile
        logger.error(res)
        return res
    
    try:
        arcname = filename if filename else '%s/%s' % (os.path.normpath(updatedir), os.listdir(updatedir)[0])
    except Exception as err:
        res = 'Update failed, no files: %s' % err
        logger.debug(res)
        return res
    if os.path.exists(arcname):
        res = 'Update source: %s' % arcname
        #Create flag file
        uf = open(updatefile, 'w')
        uf.write('0')
        uf.close()
        logger.debug('Update file created: %s' % updatefile)
        #Backup current system files
        res = "%s\n%s" %(res, backup())
        #Extract new version files to run directory
        tar = tarfile.open(arcname)
        fileList = tar.getnames()
        logger.debug('Files to update: %s' % fileList)
        tar.extractall(path=workdir)
        tar.close()
        os.remove(arcname)          
        res = "%s\nUpdated files:\n%s\nReloading qbot" % (res, fileList)
        reload()
        isWorking = False
    else:
        res = "%s doesn't exist. Nothing to update" % arcfile
    return res

def reload():
    """Stop system. Systemd should run it again"""
    global closing_proc
    closing_proc = os.popen('./stop_qbot.sh &')
    return 'Started: stop_qbot.sh'

def restore(arcname=None):
    """Restores the previous version or any version provided by backup/arcname[.tar.gz] and reloads qbot to apply changes"""
    global isWorking
    arcfile = '%s%s' % (backupdir, arcname) if arcname else '%s%s.tar.gz' % (backupdir, os.path.basename(os.path.normpath(maindir)))
    if not arcfile.endswith('.tar.gz'):
        arcfile = '%s.tar.gz' % arcfile
    if os.path.exists(arcfile):
        tar = tarfile.open(arcfile)
        res = 'Restoring %s' % arcfile
        logger.debug(res)
        tar.extractall()
        listFiles = tar.getnames()
        count = len(listFiles)
        res += '\n%d files restored to %s' % (count, maindir)
        logger.debug('%d files restored to %s' % (count, maindir))
        if os.path.exists(updatefile):
            os.remove(updatefile)
        isWorking = False
    else:
        res = "Archive doesn't exist: %s" % arcfile
        logger.error(res)
    return res
    
def approveUpdate():
    """Approves last update (removes update_flag file)"""
    global isUpdating
    res = ''
    if os.path.exists(updatefile):
        os.remove(updatefile)
        res = "Flag removed: %s" % updatefile
        logger.debug(res)
    isUpdating = False
    res = 'OK. %s' % res
    return res

def backup(src=None, arcname=None):
    """Tar-ing and gz-ing any desired file. By defauld make backup of 'run' directory"""
    source = os.path.normpath(src) if src else os.path.normpath(maindir)
    if not os.path.exists(source):
        return 'No such file or directory: %s' % source
    listFull = ['%s/%s' % (source, x) for x in os.listdir(source)] if os.path.isdir(source) else [source]
    logger.debug('Source: %s' % source)
    #Set the archive name. Given or default
    destination = os.path.normpath(backupdir)
    tarName = '%s/%s' % (destination, os.path.basename(arcname)) if arcname else '%s/%s' % (destination, os.path.basename(source))
    tarName = tarName if tarName.endswith('.tar.gz') else '%s.tar.gz' % tarName    
    logger.debug('Creating archive: %s' % tarName)
    tar = tarfile.open(tarName, 'w:gz')
    res = tarName
    tar.add(source)
    count = len(tar.getnames())
    tar.close()
    res = "%s\n%d files saved" % (res, count)
    logger.debug("%d files saved" % (count))
    return res

def listFiles(path=None):
    """Like ls"""
    wpath = path if path else workdir
    files = list(os.scandir(wpath))
    res = '%s:\nType, Name, Size\n------------' % wpath
    for f in files:
        type = 'f' if f.is_file() else 'd' if f.is_dir() else 's'
        size = f.stat().st_size
        res = '%s\n%s, %s, %s' % (res, type, f.name, size)
    return res

def moveFile(param):
    """Like mv"""
    #print(([x.strip() for x in param.replace(',', ' ').split(' ')]))
    fileName, newName = ([x.strip() for x in param.replace(',', ' ').split()])
    if os.path.exists(fileName):
        res = newName
        if os.path.isdir(newName):
            res = '%s/%s' % (res, os.path.basename(fileName))
        os.replace(fileName, res)
    else:
        res = "Error! %s doesn't exist" % fileName
    return res

def deleteFile(fileName):
    """Like rm"""
    if os.path.exists(fileName):
        os.remove(fileName)
        res = 'Deleted: %s' % fileName
    else:
        res = "Error! %s doesn't exist" % fileName
    return res

#Send script-initiated message
def sendMessage(msg, connectors = None):
    """Sends message to default (or provided) connectors"""
    if not connectors:
        connectors = mainConnectors
    for connector in connectors:
        for to in connector['to']:
            try:
                connector['connector'].sendMessage(msg, to['address'])
            except Exception as err:
                logger.error("Could not send message: %s" % err)
            #logger.debug("Message sent by %s" % connector['name'])
    
def process_alerts(manager):
    """Look for existing alerts from manager modules and send them to default connectors/users"""
    if manager['alert_pipe_semaphore'].is_set():
        alert = manager['alert_pipe'].recv()
        manager['alert_pipe_semaphore'].clear()
        sendMessage(alert)
        logger.debug('Alert send: %s' % alert)
    

#-------------------------------------------------------------------------------------------------------------------------------------
#Script main function
def main():
    """Main work function. Eternal loop"""
    logger.info('Qbot started, version=%s' % VERSION)
    #global variables
    global relays
    global commands
    global sensors
    global isWorking    
    global response
    global connectors, mainConnectors, managers

    #Filter 'Alive' connectors
    alive = [c['name'] for c in list(filter(lambda x: x['is_alive'], connectors))]
    startMsg = 'Qbot version %s started:\n%d/%d connectors running: %s' % (VERSION, len(alive), len(config['connectors']), alive)
    startMsg += '\n%d/%d managers running with %d commands' % (len(managers), len(config['managers']), len(commands))
    if isUpdating: #if in testing update mode
        startMsg += "\nUpdating mode. Wait %d seconds for approve" % waitForConfirm
    mainConnectors = None
    try:
        mainConnectors = list(filter(lambda x: x['default'], connectors))
        logger.debug("Default connectors: %s" % [x['name'] for x in mainConnectors])
    except Exception as err:
        logger.error("Could not get default connector: %s" % err)
    logger.info(startMsg)
    try:
        sendMessage(startMsg)
    except Exception as err:
        logger.error("Sending start message failed: %s" % (err))
    isWorking = True
    while isWorking:
        """pick commands in cycle"""
        sleep(timeout)
        #check connectors's statuses
        for c in connectors:
            #if daemon is down
            if not c['connector'].is_alive():
                if c['is_alive']: #and this just happened
                    msg = "Connector %s is DOWN!" % (c['name'])
                    logger.error(msg) #log this event
                    try:
                        sendMessage(msg) # and send the message to user
                        c['is_alive'] = False
                    except Exception as err:
                        logger.error("Sending message failed: %s" % (err))
                if not c['autorestart']:
                    continue
                try: #trying to start it again
                    #Get related config
                    conf = list(filter(lambda x: x['name'] == c['name'], config['connectors']))[0]
                    conn = init_connector(conf, queue, logger) #and try to reload daemon
                    if conn:
                        connectors.remove(c)
                        connectors.append(conn)
                        conn['is_alive'] = conn['connector'].is_alive()
                        logger.info('Connector reloaded: %s' % conn['name'])
                except Exception as err:
                    logger.error("Could not reload connector %s: %s" % (c['name'], err))
        
        #Check if managers sent alerts
        for m in managers:
            process_alerts(m)
        
        #Check the queue for new command
        if queue.empty(): #If no command - continue
            continue
        cmdObject = queue.get()
        cmdTextFull = cmdObject['command'] #Get the command text and upper it
        cmdSource = cmdObject['self'] #Get the object that has received the command
        #Parse command line. Retrieve command an its parameters
        command_prepared = getCommand(cmdTextFull)
        if not isCommandAllowed(cmdObject):
            logger.warning('Unknown user_id: %s' % cmdObject['user_id'])
            continue
        response = None
        if not command_prepared['command']:
            #If the commands failed we need save though some influence: Several commands of last hope
            if cmdTextFull == 'Reload':
                response = 'Last hope: %s' % reload()
            if cmdTextFull.startswith('Restore'):
                param = cmdTextFull[len('Restore'):].split()
                param = None if len(param) else param
                response = 'Last hope: %s' % restore(param)
            if not response:
                logger.debug('"%s": command not found' % cmdObject['command'])
                response = "Неизвестная команда '%s'\nПопробуйте 'Help'" % cmdObject['command']
        else:
            msg_id = cmdObject['message_id']
            msg_time = cmdObject['message_time']
            user_id = cmdObject['user_id']            
            logger.info("To module %s: Command='%s', params='%s', from='%s', source='%s'" % (command_prepared['command']['module'], command_prepared['command']['commandtext'], command_prepared['params'], user_id, cmdSource.name))
            response = ''
            if command_prepared['command']['module'] == __name__: #If the command from main module
                #Creating command
                try:
                    cmd = ("global response;response = %s" % (command_prepared['command']['commandline'])).replace(PARAM_STRING, command_prepared['params'])
                    logger.debug("Running: %s" % cmd)
                    exec(cmd)
                except Exception as err:
                    response = "%s\nError: %s" % (cmdTextFull, err)
                    logger.error(response)
            else:
                try:
                    manager = list(filter(lambda x: x['name'] == command_prepared['command']['module'], managers))[0]
                    cmd = command_prepared['command']['commandline'].replace(PARAM_STRING, command_prepared['params'])
                    manager['command_pipe'].send(cmd)
                    manager['command_pipe_semaphore'].set()
                    response = manager['command_pipe'].recv() #TODO: insert block with timeout and semaphore analysis to avoid crashing remote side problems
                except Exception as err:
                    response = '%s\nError: %s' % (cmdTextFull, err)
                    logger.error(response)
        #Sending reply
        if response: #if the command don't need response, it should return None
            try:
                response = str(response)
                logger.debug('Response: %s...' % response.splitlines()[0])
                cmdSource.reply(response, cmdObject) #Reply using the source object, Reply text and original command parameters
            except Exception as err:
                logger.error('response failed: %s' % err)
        
        #Check if Update is not confirmed in supposed time, roll it back
        if isUpdating and (datetime.datetime.now() - startTime).seconds > waitForConfirm:
            restore()
    logger.debug('Stopping')
    #First send stop command to all Connectors, thus stop process will be parallel
    try:
        for c in connectors:
            if c:
                c['connector'].stop()
        for m in managers:
            if m:
                m['command_pipe'].send('self.stop()')
                m['command_pipe_semaphore'].set()
        #And now waiting the connectors to stop
        #sleep(25)
        for c in connectors:
            if c:
                c['connector'].join(25)
        for m in managers:
            if m:
                m['connector'].join(5)
        reload()
    except Exception as err:
        logger.error(err)
        sys.exit(err)
    sys.exit(0)

#-------------------------------------------------------------------------------------------------------------------------------------
#Start the script
if __name__ == "__main__":
    init()
    signal.signal(signal.SIGTERM, exitFunction)
    signal.signal(signal.SIGINT, exitFunction)
    #logger.removeHandler(ch)
    main()
