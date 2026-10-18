#!/bin/sh
# Boards are read-only mounts under /app/src. Copy them into a writable project
# so the word-cloud link can use this stack's SUPERSET_PORT (board Jinja has no
# env_var). Then run the command (dct serve, or dct validate from exec).
set -eu

PROJECT=/work/project
rm -rf "$PROJECT"
mkdir -p "$PROJECT"
cp -R /app/src/. "$PROJECT/"
sed -i "s|__SUPERSET_PORT__|${SUPERSET_PORT:-8088}|g" "$PROJECT/charts/words.yml"
cd "$PROJECT"
exec "$@"
