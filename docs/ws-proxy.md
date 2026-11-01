# WebSocket-to-TCP tunnel (browser clients)

Browser clients cannot open raw SMTP/IMAP sockets. The overlay runs a
WebSocket-to-TCP bridge so the same relay serves browser and native clients.

## Why not plain websockets to the mail ports

Mail protocols are line/stream conversations with their own TLS expectations.
The tunnel translates: the browser speaks WebSocket to the relay origin, the
bridge relays bytes to the real IMAP/SMTP listeners, TLS to the backend stays
inside the box.

## The contract (C3)

| WS path | Bridges to | Used for |
|---|---|---|
| `/imap` | IMAP listener | mail fetch/sync |
| `/smtp` | SMTP submission listener | mail send |
| `/tcp/{host}/{port}` | arbitrary TCP | iroh and other stream transports |
| `/dns` | DNS resolver | resolving the target of `/tcp` hops |

The core client gets these paths from the transport's metadata/config and
dials them in order — the browser client behaves like a native one from the
bridge's point of view.

## Origin allowlist

Browsers always send an `Origin` header on WS handshakes; native clients
send none. The bridge (and the nginx front) allow-list the origins that may
open the tunnel via `ws_allowed_origins` in `chatmail.ini` — empty means
same-origin only, native clients are always allowed. This is what keeps a
random web page from using your relay as a TCP proxy.

## Deployment

- Service: `velta-ws-proxy.service` (`bridge.py`), unprivileged.
- Front: nginx `velta-ws-proxy.conf` — TLS termination, `Upgrade`/`Connection`
  passthrough, per-path proxying to the bridge.
- Config source: `ws_allowed_origins` in the cmdeploy template (the baked
  `chatmail.ini` is generated — see AGENTS.md rule 2).

## Verification

```sh
curl -o /dev/null -w '%{http_code}\n' https://<relay>/generate_204   # 204
# a WS handshake with a disallowed Origin must be refused
# a WS handshake from the PWA origin must reach the bridge
```
