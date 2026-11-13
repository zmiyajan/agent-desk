#!/usr/bin/env python3
"""Host metrics for Agent Desk: samples /proc every 30 s, keeps 24 h in memory, serves JSON at /stats/api.

It describes the machine Docker runs on (on macOS and Windows that is Docker's Linux VM), read from the host's
/proc mounted read-only at $PROC. Disk figures are for the filesystem behind $DISK_PATH (the shared workspace).
No Docker access, nothing written to disk.
"""
import json, os, threading, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROC = os.environ.get("PROC", "/proc")
DISK_PATH = os.environ.get("DISK_PATH", "/")
STEP, KEEP = 30, 2880
hist = deque(maxlen=KEEP)
SKIP_NET = ("lo", "docker", "br-", "veth", "tailscale", "virbr", "cni", "flannel")


def cpu():
    v = list(map(int, open(f"{PROC}/stat").readline().split()[1:9]))
    return sum(v), v[3] + v[4]


def mem():
    d = {l.split(":")[0]: int(l.split()[1]) for l in open(f"{PROC}/meminfo")}
    return (d["MemTotal"] * 1024, (d["MemTotal"] - d["MemAvailable"]) * 1024,
            d.get("SwapTotal", 0) * 1024, (d.get("SwapTotal", 0) - d.get("SwapFree", 0)) * 1024)


def net():
    rx = tx = 0
    # /proc/net is per network namespace; /proc/1/net is the host's own (pid 1 of the mounted host /proc)
    for l in open(f"{PROC}/1/net/dev").readlines()[2:]:
        n, r = l.split(":")
        n, f = n.strip(), r.split()
        if n.startswith(SKIP_NET):
            continue
        rx += int(f[0])
        tx += int(f[8])
    return rx, tx


def disk():
    rd = wr = 0
    for l in open(f"{PROC}/diskstats"):
        f = l.split()
        name = f[2]
        whole = (name.startswith(("sd", "vd", "xvd", "hd")) and not name[-1].isdigit()) or \
                (name.startswith(("nvme", "mmcblk")) and "p" not in name[4:])
        if whole:
            rd += int(f[5]) * 512
            wr += int(f[9]) * 512
    return rd, wr


def safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def loop():
    pc, pn, pd, pt = cpu(), safe(net, (0, 0)), safe(disk, (0, 0)), time.time()
    while True:
        time.sleep(STEP)
        c, n, d, t = cpu(), safe(net, (0, 0)), safe(disk, (0, 0)), time.time()
        dt = max(t - pt, 1e-6)
        tot = c[0] - pc[0]
        hist.append({"t": int(t), "cpu": round(100 * (1 - (c[1] - pc[1]) / tot), 1) if tot else 0.0, "mem": mem()[1],
                     "rx": max(0, round((n[0] - pn[0]) / dt)), "tx": max(0, round((n[1] - pn[1]) / dt)),
                     "rd": max(0, round((d[0] - pd[0]) / dt)), "wr": max(0, round((d[1] - pd[1]) / dt))})
        pc, pn, pd, pt = c, n, d, t


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.split("?")[0] != "/stats/api":
            return self.send_error(404)
        m, s = mem(), os.statvfs(DISK_PATH)
        cores = sum(1 for l in open(f"{PROC}/stat") if l.startswith("cpu") and l[3].isdigit())
        body = json.dumps({
            "now": int(time.time()), "step": STEP, "cores": cores,
            "load": [float(x) for x in open(f"{PROC}/loadavg").read().split()[:3]],
            "uptime": float(open(f"{PROC}/uptime").read().split()[0]),
            "mem_total": m[0], "mem_used": m[1], "swap_total": m[2], "swap_used": m[3],
            "disk_total": s.f_blocks * s.f_frsize, "disk_used": (s.f_blocks - s.f_bfree) * s.f_frsize,
            "hist": list(hist)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


threading.Thread(target=loop, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8028), H).serve_forever()
