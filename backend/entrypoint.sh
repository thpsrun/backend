#!/bin/bash
set -euo pipefail

postgres_ready() {
    python << END
import sys

from psycopg import connect
from psycopg.errors import OperationalError

try:
    connect(
        dbname="${POSTGRES_DB}",
        user="${POSTGRES_USER}",
        password="${POSTGRES_PASSWORD}",
        host="postgres",
    )
except OperationalError:
    sys.exit(-1)
END
}

until postgres_ready; do
    >&2 echo "Waiting for PostgreSQL to become available..."
    sleep 5
done
>&2 echo "PostgreSQL is available"

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

python manage.py migrate
python manage.py collectstatic --no-input

if [ "${DEBUG_MODE:-false}" = "True" ]; then
    echo "===============STARTING IN DEVELOPMENT MODE!===============" >&2
    python manage.py runserver 0.0.0.0:${PORT:-8001} &
else
    echo "===============STARTING IN PRODUCTION MODE!===============" >&2
    gunicorn --bind 0.0.0.0:${PORT:-8001} --workers 8 website.wsgi:application &
fi

WEB_PID=$!
trap 'kill $WEB_PID' TERM INT
wait $WEB_PID
