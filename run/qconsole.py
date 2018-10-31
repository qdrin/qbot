#!/usr/bin/python3
import socket
import argparse
import os
from time import sleep

timeout = 2
parser = argparse.ArgumentParser(description='Process args for QConsole')
parser.add_argument('--port', type=int, default='49049', help='server port number')
parser.add_argument('--ip-address', default='localhost', help='IP-address of server')
args = parser.parse_args()
print (args)

sock = socket.socket()
isWorking = True
sock.connect((args.ip_address, args.port))
while isWorking:
    cmd = input('>')
    if cmd == 'quit':
        isWorking = False
    if sock._closed:
        print ('Socket closed. %s' % sock)
        os.sys.exit(0)
    if cmd == '':
        continue
    sock.send(cmd.encode())
    sleep(timeout)
    data = sock.recv(1024)
    msg = data.decode().rstrip()
    print(msg)
sock.close()
print('Exit')