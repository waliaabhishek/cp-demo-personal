#!/bin/bash

echo
echo "Start the Kafka JMX Metrics Collection application"
docker-compose up -d jmx-data-poller prometheus grafana splunk 
echo "..."

