# The agent's computer: Xfce on a virtual screen (TigerVNC), Chromium, a web terminal and the viewer.
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# Desktop + browser first (large, rarely changes), small tools after.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tigervnc-standalone-server xfce4-panel xfwm4 xfdesktop4 xfce4-settings xfce4-terminal thunar mousepad ristretto \
      papirus-icon-theme librsvg2-common dbus-x11 x11-xserver-utils x11-utils xauth \
      fonts-dejavu-core fonts-noto-core fonts-noto-color-emoji chromium \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
      novnc python3-websockify tini sudo curl ca-certificates procps git nano less python3 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Web terminal. Debian does not package ttyd, so take the upstream release binary, pinned by checksum.
ARG TARGETARCH
ARG TTYD_VERSION=1.7.7
RUN case "$TARGETARCH" in \
      amd64) a=x86_64;  h=8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55 ;; \
      arm64) a=aarch64; h=b38acadd89d1d396a0f5649aa52c539edbad07f4bc7348b27b4f4b7219dd4165 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.$a" \
 && echo "$h  /usr/local/bin/ttyd" | sha256sum -c - && chmod 755 /usr/local/bin/ttyd

# One unprivileged user owns the desktop. It may use sudo: the container is the sandbox, and an agent that
# cannot install a package is not much of a computer. Remove the sudoers line for a locked-down desk.
RUN useradd -m -u 1000 -s /bin/bash agent \
 && echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent && chmod 440 /etc/sudoers.d/agent \
 && mkdir -p /workspace && chown agent:agent /workspace

COPY desktop/start.sh /usr/local/bin/desk-start
COPY desktop/agent-browser /usr/local/bin/agent-browser
COPY desktop/cdp-relay.py /usr/local/bin/cdp-relay
COPY desktop/xfce/ /etc/desk/xfce/
COPY web/screen.html /usr/share/novnc/screen.html
RUN chmod 755 /usr/local/bin/desk-start /usr/local/bin/agent-browser /usr/local/bin/cdp-relay

USER agent
ENV HOME=/home/agent DISPLAY=:1
WORKDIR /workspace
EXPOSE 6080 7681 9223
ENTRYPOINT ["tini", "--", "desk-start"]
