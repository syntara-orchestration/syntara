#!/bin/sh
set -eu
mkdir -p /tmp/kafka-fixture
cat /fixture-certs/kafka.key /fixture-certs/kafka.crt > /tmp/kafka-fixture/server.pem
/opt/kafka/bin/kafka-storage.sh format --ignore-formatted --cluster-id MkU3OEVBNTcwNTJENDM2Qk --config /fixture/server.properties
exec /opt/kafka/bin/kafka-server-start.sh /fixture/server.properties
