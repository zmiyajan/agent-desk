#!/usr/bin/env python3
"""Sign-in for Agent Desk. Caddy asks /auth/check before every request (forward_auth).

One password (DESK_PASSWORD), a signed session cookie, nothing stored on disk.
  GET  /auth/check    200 when the session cookie is valid, else 401
  GET  /auth/login    the form        POST /auth/login   password -> cookie -> back to the page
  GET  /auth/logout
Why a cookie and not HTTP Basic auth: the screen and the terminal run over WebSockets, and browsers do not
reliably attach Basic credentials to those. A session cookie is sent with them everywhere.
"""
import base64, hashlib, hmac, html, os, secrets, sys, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASSWORD = os.environ.get("DESK_PASSWORD", "")
NAME = os.environ.get("DESK_NAME", "Agent Desk")
if len(PASSWORD) < 12:
    sys.exit("auth: DESK_PASSWORD must be at least 12 characters (the page gives a shell on the desktop). Not starting.")
SECRET = (os.environ.get("DESK_SECRET") or secrets.token_hex(32)).encode()
TTL = 7 * 86400
COOKIE = "desk_session"
fails = {}          # ip -> [timestamps] of wrong passwords


def sign(exp):
    return base64.urlsafe_b64encode(hmac.new(SECRET, str(exp).encode(), hashlib.sha256).digest()).decode().rstrip("=")


def valid(cookie_header):
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE and "." in v:
            exp, sig = v.split(".", 1)
            if exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, sign(exp)):
                return True
    return False


def safe_rd(rd):
    """Only ever send people back to a path on this site."""
    return rd if rd.startswith("/") and not rd.startswith("//") and "\\" not in rd and "\n" not in rd else "/"


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0f0f10"><title>%(name)s · Sign in</title><style>
*{box-sizing:border-box}html,body{height:100%%;margin:0;background:#0f0f10;color:#f5f5f7;-webkit-font-smoothing:antialiased;
font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif}
body{display:flex;align-items:center;justify-content:center;padding:24px}
form{width:100%%;max-width:340px;background:#161617;border:1px solid #2a2a2d;border-radius:14px;padding:26px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.02em}p{margin:0 0 20px;color:#a1a1a6;font-size:14px}
input{width:100%%;height:42px;padding:0 13px;border:1px solid #3a3a3e;border-radius:9px;background:#0c0c0d;color:inherit;font:inherit}
input:focus{outline:2px solid #0a84ff;outline-offset:1px}
button{width:100%%;height:42px;margin-top:12px;border:0;border-radius:9px;background:#f5f5f7;color:#111;font:inherit;font-weight:600;cursor:pointer}
.err{color:#ff453a;font-size:13.5px;margin:12px 0 0;min-height:18px}
</style></head><body><form method="post" action="/auth/login"><h1>%(name)s</h1><p>Sign in to open the agent's desk.</p>
<input type="hidden" name="rd" value="%(rd)s"><input type="password" name="password" placeholder="Password" autocomplete="current-password" autofocus required>
<button>Sign in</button><div class="err">%(err)s</div></form></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def ip(self):
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def page(self, code, rd, err=""):
        b = (PAGE % {"name": html.escape(NAME), "rd": html.escape(rd, quote=True), "err": html.escape(err)}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def redirect(self, to, cookie=None):
        self.send_response(303)
        self.send_header("Location", to)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/auth/check":
            ok = valid(self.headers.get("Cookie"))
            self.send_response(200 if ok else 401)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if u.path == "/auth/logout":
            return self.redirect("/auth/login", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        if u.path == "/auth/login":
            rd = safe_rd(urllib.parse.parse_qs(u.query).get("rd", ["/"])[0])
            return self.redirect(rd) if valid(self.headers.get("Cookie")) else self.page(200, rd)
        self.send_error(404)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/auth/login":
            return self.send_error(404)
        n = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
        form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        rd = safe_rd(form.get("rd", ["/"])[0])
        ip, now = self.ip(), time.time()
        recent = [t for t in fails.get(ip, []) if now - t < 300]
        if len(recent) >= 5:
            fails[ip] = recent
            return self.page(429, rd, "Too many attempts. Wait a few minutes.")
        if not hmac.compare_digest(form.get("password", [""])[0].encode(), PASSWORD.encode()):
            fails[ip] = recent + [now]
            time.sleep(0.5)
            return self.page(401, rd, "Wrong password.")
        fails.pop(ip, None)
        exp = int(now) + TTL
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        self.redirect(rd, f"{COOKIE}={exp}.{sign(exp)}; Path=/; Max-Age={TTL}; HttpOnly; SameSite=Lax{secure}")


ThreadingHTTPServer(("0.0.0.0", 9000), H).serve_forever()
