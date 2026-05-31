#!/bin/bash
# Start the intelligence API. Loads .env, forces the plain asyncio loop
# (uvloop hangs asyncmy over the cross-border tunnel).
cd /home/suuuu/develop/intelligence-system || exit 1
set -a
. ./.env 2>/dev/null
set +a
exec .venv/bin/uvicorn src.main:app \
  --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8100}" --loop asyncio
