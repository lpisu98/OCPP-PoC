#!/bin/bash
set -e

echo "Starting database service..."
docker-compose up -d db

echo "Waiting for database to be healthy..."
./wait-for-db.sh

echo "Building app service..."
docker-compose build app

echo "Starting all services..."
docker-compose up
