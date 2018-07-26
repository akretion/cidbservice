#!/bin/bash

USER_ID=$(stat -c '%u' /var/run/postgresql)
SERVICE="cidbservice.app.celery"
useradd -u $USER_ID $POSTGRES_USER
celery worker -A $SERVICE --loglevel=INFO
pip show cidbservice
