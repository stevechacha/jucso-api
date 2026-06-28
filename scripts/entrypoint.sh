#!/bin/sh
set -e

python manage.py migrate

if [ "${SEED_DATA}" = "true" ]; then
  echo "SEED_DATA=true — loading demo seed data"
  python manage.py seed_jucso
fi

exec gunicorn jucso_api.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
