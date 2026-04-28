#!/bin/sh
set -eu

URL="${KIOSK_URL:-http://localhost:8000/playback}"
REMOTE_DEBUGGING="${ENABLE_REMOTE_DEBUGGING:-false}"
DISABLE_WEB_SECURITY="${KIOSK_DISABLE_WEB_SECURITY:-false}"

DEBUG_FLAG=""
if [ "$REMOTE_DEBUGGING" = "true" ]; then
  DEBUG_FLAG="--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222"
fi

SECURITY_BYPASS_FLAGS=""
if [ "$DISABLE_WEB_SECURITY" = "true" ]; then
  SECURITY_BYPASS_FLAGS="--disable-web-security --disable-site-isolation-trials --disable-features=IsolateOrigins,site-per-process --allow-running-insecure-content --ignore-certificate-errors"
fi

while true; do
  chromium \
    --kiosk \
    --no-first-run \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    --disable-pinch \
    --incognito \
    $DEBUG_FLAG \
    $SECURITY_BYPASS_FLAGS \
    "$URL"
  sleep 2
done
