#!/bin/bash

USER_ID=$(stat -c '%u' /var/run/postgresql)
WSGI="cidbservice.app:create_app()"
useradd -u $USER_ID $POSTGRES_USER
gunicorn -b $SERVICE_HOST:$SERVICE_PORT \
    --access-logfile - \
    $WSGI \
    --user $POSTGRES_USER \
    --group $POSTGRES_GROUP
