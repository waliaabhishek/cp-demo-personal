#!/bin/bash

# TODO : Work on determining if the docker Override file is active or not and only then execute the following docker-compose commands.
echo
echo "Start the Kafka JMX Metrics Collection application"
docker-compose up -d jmx-data-poller prometheus grafana splunk 
echo "..."

