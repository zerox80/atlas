#!/bin/sh
set -e

# Run database migrations
python migrate_db.py

# Start the application
exec uvicorn main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
