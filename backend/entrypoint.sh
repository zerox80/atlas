#!/bin/sh
set -e

# Schema creation and migrations run in the application startup hook.
exec uvicorn main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-172.30.253.0/24}"
