#!/bin/bash
# Starts the desk: virtual screen, Xfce, the screen bridge, the web terminal and the browser relay.
# If any of them exits, the container exits and Docker restarts it.
set -uo pipefail

GEOM="${DESK_GEOMETRY:-1600x900}"
export DISPLAY=:1 HOME=/home/agent USER=agent
export XDG_CONFIG_HOME="$HOME/.config" XDG_CACHE_HOME="$HOME/.cache" XDG_DATA_HOME="$HOME/.local/share"
export XDG_RUNTIME_DIR="/tmp/runtime-agent" XDG_CURRENT_DESKTOP=XFCE XDG_SESSION_TYPE=x11 GDK_BACKEND=x11 NO_AT_BRIDGE=1
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"

# First start: put the desk's layout in place. Later edits made in the desktop itself are kept.
X="$XDG_CONFIG_HOME/xfce4/xfconf/xfce-perchannel-xml"
if [ ! -e "$X/xfce4-panel.xml" ]; then
  mkdir -p "$X" "$XDG_CONFIG_HOME/xfce4/panel" "$HOME/Desktop"
  cp /etc/desk/xfce/*.xml "$X/"
  cp -r /etc/desk/xfce/panel/. "$XDG_CONFIG_HOME/xfce4/panel/"
  ln -sfn /workspace "$HOME/Desktop/Workspace"
fi
sudo -n chown agent:agent /workspace 2>/dev/null || true

# Virtual screen. VNC listens on loopback only; the bridge below is the only way in.
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
Xvnc :1 -geometry "$GEOM" -depth 24 -dpi 96 -rfbport 5901 -localhost -SecurityTypes None -AlwaysShared \
     -AcceptSetDesktopSize=0 -FrameRate 30 -SendCutText=0 -desktop "desk" -nolisten tcp 2>/dev/null &
for _ in $(seq 1 100); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done
xdpyinfo >/dev/null 2>&1 || { echo "desk: the virtual screen did not start" >&2; exit 1; }
xset s off -dpms s noblank 2>/dev/null || true

# Xfce, component by component (no session manager: there is no login session inside a container).
dbus-run-session -- bash -c '
  xfsettingsd --sm-client-disable --daemon 2>/dev/null
  xfwm4 --compositor=off --sm-client-disable &
  for _ in $(seq 1 50); do xprop -root _NET_SUPPORTING_WM_CHECK >/dev/null 2>&1 && break; sleep 0.1; done
  xfdesktop --sm-client-disable --disable-wm-check &
  xfce4-panel --sm-client-disable --disable-wm-check &
  if [ "${DESK_BROWSER_AUTOSTART:-1}" = "1" ]; then (sleep 2; agent-browser about:blank >/dev/null 2>&1) & fi
  wait
' &

websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5901 >/dev/null 2>&1 &
( cd /workspace && exec ttyd -i 0.0.0.0 -p 7681 -b /term -O -W -t rendererType=dom -t fontSize=13 -t lineHeight=1.25 \
    -t 'fontFamily=SF Mono,Menlo,Monaco,Consolas,monospace' -t titleFixed=Terminal -t disableLeaveAlert=true \
    -t 'theme={"background":"#000000","foreground":"#e5e5ea","cursor":"#0a84ff"}' bash -l ) >/dev/null 2>&1 &
cdp-relay >/dev/null 2>&1 &

echo "desk: screen ${GEOM} ready"
wait -n
echo "desk: a component stopped; restarting the container" >&2
exit 1
