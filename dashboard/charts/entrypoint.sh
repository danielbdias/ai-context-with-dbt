#!/bin/sh
# Boards are read-only mounts under /app/src. Copy them into a writable project,
# because dct writes next to the boards. Then run the command (dct serve, or
# dct validate from exec).
set -eu

PROJECT=/work/project
rm -rf "$PROJECT"
mkdir -p "$PROJECT"
cp -R /app/src/. "$PROJECT/"
cd "$PROJECT"
exec "$@"
