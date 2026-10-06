# websockify mail endpoints (Velta C3)

Mail-over-WebSocket on the relay's HTTPS origin, in two shapes:

1. **Fixed paths** (upstream PR #1030 shape): `/imap`, `/smtp` — nginx
   WS-upgrade → websockify → the **TLS** mail ports:

| endpoint | nginx (TLS, public) | websockify (loopback) | service |
|---|---|---|---|
| `/imap` | 443 wss | 127.0.0.1:8143 → localhost:993 | Dovecot IMAPS |
| `/smtp` | 443 wss | 127.0.0.1:8587 → localhost:465 | Postfix submission (smtps) |

2. **Velta wasm-core bridge scheme** (core patch 0007): the core dials
   `{proxy}/tcp/{host}/{port}` for TCP and `{proxy}/dns/{host}` for DNS.
   nginx routes `/tcp/.../993` and `/tcp/.../465` to the same two
   websockify units (the `{host}` path part is ignored — the tunnel always
   lands on the relay's own mail services) and `/dns/` to a tiny
   DNS-over-WebSocket bridge (`ws-dns-bridge.py`, port 8153) that answers
   the first WS message with a JSON IP array for the relay's own domain
   only.

Upstream basis: chatmail/relay PR #1030 (`02c7d3d`). Velta additions:
Origin allowlist, per-IP connection cap, `/new` CORS, TLS-port targets,
and the `/tcp/`+`/dns/` bridge scheme — all driven by the
`ws_allowed_origins` chatmail.ini parameter (comma-separated https
origins, empty = same-origin only).

## Security model

- **TLS topology (TLS stays in the client):** the browser↔nginx leg is wss
  (the relay's normal certificate); INSIDE the tunnel the client runs the
  mail session's own TLS (rustls in the wasm sandbox) against the relay's
  real certificate on 993/465. The proxy never terminates mail-layer TLS
  and never sees plaintext credentials outside the loopback legs. This is
  why the units target the TLS ports, unlike upstream's plaintext
  143/587 model for non-TLS web clients.
- **Origin model:** browsers always send an `Origin` header on WebSocket
  handshakes; nginx rejects handshakes whose origin is not in
  `ws_allowed_origins` (403). Requests without an Origin header (native
  Delta Chat, websocat) are always allowed — this endpoint is exactly the
  native IMAP/SMTP path, just over wss.
- **Port confinement:** the `/tcp/` scheme only dials 993 and 465 — never
  25 or any other port; the `{host}` path part is ignored (the tunnel
  always lands on this relay's own mail services).
- **DNS:** `/dns/{host}` resolves only the relay's own mail domain
  (suffix match) and answers a single JSON IP array — not an open
  resolver.
- **Per-IP accounting caveat:** every WebSocket client arrives at Dovecot/
  Postfix from 127.0.0.1 (the websockify hop), so relay-side per-IP limits
  and HELO checks see one shared loopback peer, and the SMTP `HELO/EHLO`
  name is the client-declared string, not resolvable per browser. The
  compensating control is nginx's `limit_conn wsmail_conn` (10 concurrent
  tunnels per client IP, sized for a few tabs per device) plus Postfix/
  Dovecot's global process limits (`max_imap_connections`,
  `max_smtp_connections`).
- **Account minting:** `/new` carries `Access-Control-Allow-Origin` for
  allowlisted origins only, so a browser PWA can mint accounts without a
  server-side proxy. The mint response carries no credentials beyond the
  one-time address/password pair, and no cookies are involved.
