#!/bin/bash
#Starts qbot service

#If found update_flag and its value more than zero
#we should suppose that updated version of qbot could not start at all
#So we need to restore previous version
if [ -f 'update_flag' ]; then
	i=`cat update_flag`
	echo "qbot is in updating mode. Num of starts: $i"
	if [ $i -ne "0" ]; then
		echo "Restoring previous version"
		tar -xf backup/run.tar.gz 
		rm update_flag
	else
		i=$(($i+1))
		echo "Num of starts: $i"
		echo $i > update_flag
	fi
else
	echo "Starting in normal mode"
fi
/usr/bin/python3 run/qbot.py

echo "Exit now"
exit 1
