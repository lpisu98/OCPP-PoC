#!/bin/bash
set -e

TIMEOUT=60
ELAPSED=0
INTERVAL=5

while [ $ELAPSED -lt $TIMEOUT ]; do
  if docker-compose exec -T db mysqladmin ping -h localhost -u steve -pchangeme &> /dev/null; then
    echo "Database is ready!"
    exit 0
  fi
  echo "Waiting for database... ($ELAPSED/$TIMEOUT)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo "Database failed to start within $TIMEOUT seconds"
exit 1
