#!/usr/bin/env python3
"""Smallest possible agent: connect to the desk's browser over CDP and open a page.

No dependencies (standard library only), so it runs in any Python image. A real agent would use Playwright,
Puppeteer or browser-use with the same address: http://desktop:9223
"""
import base64, json, os, socket, struct, time, urllib.request

CDP = os.environ.get("DESK_CDP", "http://desktop:9223")
URL = os.environ.get("OPEN_URL", "https://example.com")


def get(path):
    return json.load(urllib.request.urlopen(CDP + path, timeout=10))


for _ in range(30):                      # the browser needs a moment after the desk starts
    try:
        version = get("/json/version")
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("could not reach the desk's browser at " + CDP)
print("browser:", version["Browser"])

page = next(t for t in get("/json/list") if t["type"] == "page")
ws_url = page["webSocketDebuggerUrl"]
host, _, path = ws_url[len("ws://"):].partition("/")
name, _, port = host.partition(":")

sock = socket.create_connection((name, int(port or 80)), timeout=10)
key = base64.b64encode(os.urandom(16)).decode()
sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
              f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
assert b" 101 " in sock.recv(4096), "WebSocket handshake failed"


def send(obj):
    data = json.dumps(obj).encode()
    mask = os.urandom(4)
    head = bytes([0x81]) + (bytes([0x80 | len(data)]) if len(data) < 126 else bytes([0x80 | 126]) + struct.pack(">H", len(data)))
    sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


send({"id": 1, "method": "Page.navigate", "params": {"url": URL}})
time.sleep(3)
print("opened", URL, "on the desk. Look at the Computer tab.")
with open("/workspace/agent-was-here.txt", "w") as fh:
    fh.write(f"The example agent opened {URL} at {time.strftime('%Y-%m-%d %H:%M:%S')}.\n")
print("wrote /workspace/agent-was-here.txt. Look at the Filesystem tab.")
