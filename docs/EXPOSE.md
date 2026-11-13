# Reaching the desk from another device

By default the page answers only on `127.0.0.1:8080` of the machine that runs Docker. Two safe ways to open it up.

## A private network (recommended)

Put the server on a private network such as Tailscale or WireGuard and bind the page to that address only:

```sh
# .env
DESK_BIND=100.x.y.z      # the server's private address
```

Only devices on your private network can reach it. Add TLS as below if you want `https://`.

## TLS in front

Run a reverse proxy with a certificate on the host and point it at `127.0.0.1:8080`. With Caddy on the host:

```
desk.example.com {
	reverse_proxy 127.0.0.1:8080
}
```

The session cookie is marked `Secure` automatically when the proxy sends `X-Forwarded-Proto: https` (Caddy does).
WebSockets (screen and terminal) need no extra configuration.

## What not to do

- Do not set `DESK_BIND=0.0.0.0` on a machine with a public address and no TLS: the password would travel in
  clear text, and the page is a shell.
- Do not publish ports 6080, 7681 or 9223. They have no authentication of their own.

## Stronger sign-in

`auth/server.py` is deliberately small: one password and a signed cookie. To use passkeys or single sign-on,
replace it with any service that answers Caddy's `forward_auth` (for example oauth2-proxy in front of an OIDC
provider) and keep the `/auth/check` contract: 2xx when signed in, 401 otherwise.
