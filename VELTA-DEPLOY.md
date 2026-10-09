# Velta relay overlay — what this deployment adds on top of stock chatmail

This repository tracks the chatmail base. The deployed relay runs stock
chatmail **plus a Velta overlay** that currently exists as hand-applied
configuration on the server (backporting it into the `cmdeploy`
templates is tracked as TODO — see the end). This document is the
authoritative list of the overlay pieces, why they exist, and how to
reproduce them on a fresh box. Placeholders: `<relay-domain>`,
`<relay-ip>` — never deploy real private hostnames into public repos.

## The pieces

### 1. C3 WebSocket mail tunnel (browser clients)

Browsers cannot open raw TCP, so the PWA (wasm Delta Chat core) tunnels
IMAP/SMTP over WebSockets and terminates TLS inside the client. Three
loopback services:

| Service | Listen | Upstream | Purpose |
|---|---|---|---|
| `websockify` | 127.0.0.1:8143 | localhost:993 (imaps) | `/tcp/{host}/993` tunnels |
| `websockify` | 127.0.0.1:8587 | localhost:465 (submission) | `/tcp/{host}/465` tunnels |
| `ws-dns-bridge.py` | 127.0.0.1:8153 | — | answers `wss://<relay>/dns/<host>` with `["127.0.0.1"]` for the relay's own domain, `[]` for everything else (anti-open-proxy: nginx ignores the host part of `/tcp/` and dials the relay's own services) |

nginx (HTTPS server block):

```nginx
# origin allowlist: browsers always send Origin on WS handshakes;
# native clients send none and are always allowed
map $http_origin $wsmail_origin_ok {
    default 0;
    "" 1;
    "https://<pwa-origin>" 1;
}
limit_conn_zone $binary_remote_addr zone=wsmail_conn:10m;

location ~ ^/tcp/[^/]+/993$ {
    if ($wsmail_origin_ok = 0) { return 403; }
    limit_conn wsmail_conn 10;
    proxy_pass http://127.0.0.1:8143;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
location ~ ^/tcp/[^/]+/465$ { ... proxy_pass http://127.0.0.1:8587; ... }
location /dns/ { ... proxy_pass http://127.0.0.1:8153; ... }
```

**Deploy as systemd units, not bare processes** — the current box ran
them from a shell for days and a reboot would silently kill browser mail.

### 2. Invite-only account creation

Open signup is closed (`/new` and `/cgi-bin/newemail.py` → `403`); the
only path is a single-use invite link `https://<relay-domain>/i/<token>`.
Two-file CGI + CLI, full deploy/usage/troubleshooting doc lives in the
velta repo: `scripts/relay-invite/README.md`. nginx adds `location /i/`
(fastcgi) and the two 403 blocks.

### 3. PWA hosting

The Velta web app is served from `/app/` (static dist built by the velta
repo's `scripts/build-pwa.mjs`). The precache service worker MUST stay at
the app root (`/app/sw.js`) for scope. Dists never contain private
hostnames (`wsProxyUrl: ""`); users add relays in-app.

### 4. Inbound HTTPS federation (`/mxdeliv`)

Relay-to-relay mail over HTTPS instead of SMTP:25 — receiver behind nginx
(size-capped) feeding the fork's `filtermail`, DKIM-domain-alignment
enforced. See `docs/research/https-federation-plan.md` in the velta repo
for the staged plan, acceptance tests, and the operational findings
(outbound port 25 + PTR recipe included).

### 5. iroh relay

The iroh 1.0 relay co-hosts on its own TLS port (3341) — separate server
block, `location /relay` proxying the local iroh service.

### 6. www pages

`www/` builds the info/privacy pages. Hygiene rule: no personal e-mail
in `privacy_mail`/`mail_server_admin` (both feed public pages and IMAP
metadata `/shared/admin`); empty values render fine after the template
tweaks noted in the velta repo's docs.

## Hosting prerequisites (order matters)

1. DNS: apex **A record, grey-cloud/direct** (a proxied apex kills
   25/465/993; the DC core has no SRV support), MX → self, SPF/DMARC
   strict, DKIM TXT (selector from `opendkim.conf`).
2. Hoster: **unblock outbound port 25** (commonly filtered by default —
   inbound works, outbound silently drops) and set **PTR/rDNS** for
   `<relay-ip>` → `<relay-domain>`. Without PTR, strict receivers
   (Yandex-class) tarpit or 450 you even with 25 open.
   Checking 25 properly: read ONE greeting line with its own timeout —
   `timeout 10 bash -c 'exec 3<>/dev/tcp/mx.google.com/25; timeout 5 head -1 <&3'`
   → `220 … ESMTP` = open. (`head -c 80` waits for 80 bytes and lies.)
3. TLS: Let's Encrypt for the mail domain (acme_email stays private).

## Post-deploy verification

- `grep proxy-reject /var/log/mail.log` (ISO timestamps!) after a test
  send to an external recipient; SASL auth OK + `451` at END-OF-MESSAGE
  means auth is fine and the outbound leg is not.
- WebSocket dials: websockify logs `Path: '/tcp/127.0.0.1/993'` per
  client connect.
- Invite E2E: the recipe in the velta repo's invite README.
- Federation inbound: send from a peer relay, expect `proxy-accept 250`.

## TODO / backlog

- Backport the overlay (nginx template blocks, ws services as systemd
  units, invite CGI, 403 blocks) into this repo's `cmdeploy` templates so
  a fresh box needs no hand edits.
- Outbound HTTPS-first transport for non-fork peers; Web Push for the
  PWA; UnifiedPush notifier for Android (see velta issue #110 +
  `PLAN-UNIFIEDPUSH.MD`).
