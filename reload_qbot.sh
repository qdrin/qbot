#!/bin/bash
#reload qbot service
./stop_qbot.sh $1
echo "Stopped. Starting"

./start_qbot.sh &
echo "Started"
