# websockify mail endpoints (Velta C3)

`/imap` and `/smtp` are WebSocket-to-TCP tunnels on the relay's HTTPS origin
(nginx WS-upgrade → websockify → loopback mail services):

| endpoint | nginx (TLS, public) | websockify (loopback) | service |
|---|---|---|---|
| `/imap` | 443 wss | 127.0.0.1:8143 → localhost:143 | Dovecot IMAP |
| `/smtp` | 443 wss | 127.0.0.1:8587 → localhost:587 | Postfix submission |

Upstream basis: chatmail/relay PR #1030 (`02c7d3d`). Velta additions:
Origin allowlist, per-IP connection cap, `/new` CORS — all driven by the
`ws_allowed_origins` chatmail.ini parameter (comma-separated https origins,
empty = same-origin only).

## Security model

- **TLS topology:** the browser↔nginx leg is wss (the relay's normal
  certificate). Inside the tunnel the mail protocols run as they would from
  localhost: IMAP on 143 is plaintext-on-loopback; submission on 587
  requires STARTTLS, which the client performs end-to-end through the
  tunnel — the proxy never sees plaintext credentials outside loopback and
  never terminates mail-layer TLS itself.
- **Origin model:** browsers always send an `Origin` header on WebSocket
  handshakes; nginx rejects handshakes whose origin is not in
  `ws_allowed_origins` (403). Requests without an Origin header (native
  Delta Chat, websocat) are always allowed — this endpoint is exactly the
  native IMAP/SMTP path, just over wss.
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
