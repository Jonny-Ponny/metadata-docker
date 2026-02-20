#!/bin/bash
set -e

if [ ! -z "$PUID" ] && [ ! -z "$PGID" ]; then
    echo "Setting user to PUID:$PUID and PGID:$PGID"
    
    if getent group "$PGID" > /dev/null 2>&1; then
        GROUP_NAME=$(getent group "$PGID" | cut -d: -f1)
    else
        GROUP_NAME="appgroup"
        addgroup -g "$PGID" "$GROUP_NAME"
    fi
    
    if getent passwd "$PUID" > /dev/null 2>&1; then
        USER_NAME=$(getent passwd "$PUID" | cut -d: -f1)
        usermod -g "$GROUP_NAME" "$USER_NAME"
    else
        USER_NAME="appuser"
        adduser -u "$PUID" -G "$GROUP_NAME" -D -H "$USER_NAME"
    fi
    
    chown -R "$PUID":"$PGID" /app /music /logs
    echo "Starting gunicorn as user $USER_NAME..."
    exec gosu "$USER_NAME" gunicorn --bind 0.0.0.0:${CONTAINER_PORT:-5000} --workers 1 --threads 8 app:app
else
    echo "PUID/PGID not set, running as root"
    exec gunicorn --bind 0.0.0.0:${CONTAINER_PORT:-5000} --workers 1 --threads 8 app:app
fi
