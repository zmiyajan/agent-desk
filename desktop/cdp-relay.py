#!/usr/bin/env python3
"""Lets other containers drive the desk's browser: 0.0.0.0:9223 -> Chromium's debugging port on 127.0.0.1:9222.

Chromium only answers DevTools requests whose Host header is an IP address or localhost, and the WebSocket
addresses it hands out point at 127.0.0.1. So a plain port forward is not enough for `http://desktop:9223`:
this relay rewrites the Host header on the way in and the advertised addresses on the way out.
The port is not published by compose; only containers on the `desk` network can reach it.
"""
import asyncio

UP = ("127.0.0.1", 9222)
LOCAL = (b"127.0.0.1:9222", b"localhost:9222")


async def pipe(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle(r, w):
    try:
        head = await asyncio.wait_for(r.readuntil(b"\r\n\r\n"), 15)
        first, rest = head.split(b"\r\n", 1)
        lines = [l for l in rest.split(b"\r\n") if l]
        host = next((l.split(b":", 1)[1].strip() for l in lines if l.lower().startswith(b"host:")), b"desktop:9223")
        upgrade = b"upgrade: websocket" in head.lower()
        lines = [l for l in lines if not l.lower().startswith((b"host:", b"connection:") if not upgrade else (b"host:",))]
        lines.append(b"Host: " + LOCAL[0])
        if not upgrade:
            lines.append(b"Connection: close")
        ur, uw = await asyncio.open_connection(*UP)
        uw.write(first + b"\r\n" + b"\r\n".join(lines) + b"\r\n\r\n")
        await uw.drain()
        if upgrade:
            await asyncio.gather(pipe(r, uw), pipe(ur, w))
            return
        n = next((int(l.split(b":")[1]) for l in lines if l.lower().startswith(b"content-length:")), 0)
        if n:
            uw.write(await r.readexactly(n))
            await uw.drain()
        # Chromium keeps the connection open, so read exactly one response: headers, then Content-Length bytes.
        h = (await asyncio.wait_for(ur.readuntil(b"\r\n\r\n"), 15))[:-4]
        size = next((int(l.split(b":")[1]) for l in h.split(b"\r\n") if l.lower().startswith(b"content-length:")), 0)
        body = await asyncio.wait_for(ur.readexactly(size), 15) if size else b""
        uw.close()
        for a in LOCAL:
            body = body.replace(a, host)               # ws://127.0.0.1:9222/... -> ws://<what the caller used>/...
        hl = [l for l in h.split(b"\r\n") if not l.lower().startswith(b"content-length:")]
        w.write(b"\r\n".join(hl) + b"\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        await w.drain()
    except Exception:
        try:
            w.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await w.drain()
        except Exception:
            pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", 9223)
    async with server:
        await server.serve_forever()


asyncio.run(main())
