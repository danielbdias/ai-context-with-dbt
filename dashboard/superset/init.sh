#!/bin/bash
# One-shot provisioning for the Superset service, run before the server starts.
# Safe to re-run: migrations and roles are idempotent, the admin is created only
# when missing, and the bundle is imported by its stable UUIDs.
set -euo pipefail

BUNDLE_ZIP="$(mktemp --suffix=.zip)"
trap 'rm -f "$BUNDLE_ZIP"' EXIT

echo "Applying Superset metadata migrations"
superset db upgrade

if superset fab list-users | grep -q "username:admin "; then
    echo "Admin user already exists"
else
    superset fab create-admin \
        --username admin \
        --email admin@example.com \
        --password "$SUPERSET_ADMIN_PASSWORD" \
        --firstname Superset \
        --lastname Admin
fi

echo "Creating roles and permissions"
superset init

echo "Importing the word-cloud bundle"
python /app/aictx/render_bundle.py "$BUNDLE_ZIP"
superset import-dashboards -p "$BUNDLE_ZIP" -u admin
echo "Superset provisioning complete"
