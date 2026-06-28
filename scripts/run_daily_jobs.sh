#!/bin/sh
set -e

echo "Running JUCSO daily maintenance jobs…"
python manage.py export_portal_backup --output "${BACKUP_OUTPUT_PATH:-/tmp/jucso-backup.json}"
python manage.py notify_overdue_complaints
python manage.py notify_overdue_suggestions
echo "Daily maintenance jobs complete."
