#!/bin/bash
#Stops qbot service

max_wait=45 #max time to wait for stopping the service

#First get qbot pid from pid file
python_pid=$(cat `grep PIDFile /etc/systemd/system/qbot.service | awk -F '=' '{print $2}'`)
#if process is not running consider it already stopped
if [ -z $python_pid ]; then
	echo "PID '$python_pid' does not exist. Nothing to stop"
	exit 0
fi

#Send SIGINT to service and wait for it correct exit
echo "Stopping qbot. MAINPID=$1, python_pid=$python_pid, USER=$USER"
/bin/kill -s SIGINT $python_pid
echo "Sighal passed"
for (( i=0; i < $max_wait; i++ )) #vk_api needs waiting for closing connection (standard time for events 'check' is 25 secs and 10 secs - for socket, email and console)
do
#Check if process stopped every second and exit without errors
	p=`ps -o pid --no-headers $python_pid`
	if ! [ -n "$p" ]; then
        	echo "qbot has been stopped. PID '$p' is null"
        	exit 0
	fi	
	sleep 1s
done

#if correct exit failed kill process roughly
echo "Error! qbot could not  be stopped politely"
kill -9 $python_pid
exit 1
