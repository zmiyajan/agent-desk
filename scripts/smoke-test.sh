#!/bin/sh
# End-to-end check of a running stack. Uses the password from .env. Exits non-zero on the first failure.
set -eu
cd "$(dirname "$0")/.."
PORT=$(grep -E '^DESK_PORT=' .env 2>/dev/null | cut -d= -f2 | cut -d' ' -f1); PORT=${PORT:-8080}
PASS=$(grep -E '^DESK_PASSWORD=' .env | cut -d= -f2-)
B="http://127.0.0.1:$PORT"; JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT
ok() { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; exit 1; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "signed out"
for p in / /screen/screen.html /term/ /files/api/resources/ /stats/api; do
  [ "$(code "$B$p")" = 302 ] && ok "$p redirects to sign-in" || fail "$p is reachable without signing in"
done
[ "$(code -X POST -d 'password=wrong-password-xx' "$B/auth/login")" = 401 ] && ok "wrong password is refused" || fail "wrong password was not refused"

echo "signed in"
[ "$(code -c "$JAR" -X POST --data-urlencode "password=$PASS" "$B/auth/login")" = 303 ] && ok "sign-in" || fail "sign-in with DESK_PASSWORD"
[ "$(code -b "$JAR" "$B/")" = 200 ] && ok "page" || fail "page"
[ "$(code -b "$JAR" "$B/screen/screen.html")" = 200 ] && ok "screen viewer" || fail "screen viewer"
[ "$(code -b "$JAR" "$B/term/")" = 200 ] && ok "terminal" || fail "terminal"
curl -s -b "$JAR" "$B/stats/api" | grep -q '"mem_total"' && ok "metrics" || fail "metrics"
T=$(curl -s -b "$JAR" -X POST "$B/files/api/login"); [ "${#T}" -gt 100 ] && ok "file API" || fail "file API"
WS="Connection: Upgrade"; UP="Upgrade: websocket"; V="Sec-WebSocket-Version: 13"; K="Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=="
[ "$(curl -s -m 4 -o /dev/null -w '%{http_code}' -b "$JAR" -H "$WS" -H "$UP" -H "$V" -H "$K" -H 'Sec-WebSocket-Protocol: binary' "$B/screen/websockify" || true)" = 101 ] && ok "screen WebSocket" || fail "screen WebSocket"
[ "$(curl -s -m 4 -o /dev/null -w '%{http_code}' -b "$JAR" -H "$WS" -H "$UP" -H "$V" -H "$K" -H 'Sec-WebSocket-Protocol: tty' -H "Origin: $B" "$B/term/ws" || true)" = 101 ] && ok "terminal WebSocket" || fail "terminal WebSocket"

echo "inside the Docker network"
docker compose exec -T desktop sh -c 'xdpyinfo | grep -q dimensions' && ok "virtual screen" || fail "virtual screen"
docker compose exec -T stats python3 -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://desktop:9223/json/version', timeout=10))['Browser'])" >/dev/null 2>&1 \
  && ok "browser automation (CDP) from another container" || fail "browser automation (CDP) from another container"
[ "$(code "http://127.0.0.1:9223/json/version" || true)" != 200 ] && ok "CDP is not published on the host" || fail "CDP is published on the host"
echo "all checks passed"
