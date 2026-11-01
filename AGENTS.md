# AGENTS.md — rules for agents (and humans) touching this repo

This repository is the **public face of the Velta relay overlay**: upstream
chatmail plus the deployment documentation for the overlay that our
production relay runs. Everything committed here is public — treat the
private-identifier rule below as absolute.

## 1. No private identifiers — ever

This repo must never contain the relay's domain, its IP address, the hoster
name, invite tokens, account handles, or anything that points at the
production box. Before every commit run:

```sh
git grep -nE "<relay-domain>|<relay-ip>|<hoster-name>" -- .
```

The sweep must be empty. If a doc needs to name the deployment, write
"the production relay" or "the overlay deployment".

## 2. The chatmail.ini on a deployment is generated

`chatmail.ini` (and every service unit) is written by `cmdeploy` from the
templates in this repo. Hand-editing the baked file on a server is a
stop-gap that the next deploy will overwrite — the durable fix always goes
into the cmdeploy templates/source here first, then gets deployed.

## 3. Documentation map

- `VELTA-DEPLOY.md` — the overlay index: what the deployment adds on top of
  stock chatmail, hosting prerequisites, deploy checklist.
- `docs/compare.md` — capability table: upstream main vs the overlay.
- `docs/invites.md` — invite-only signup: tokens, claim flow, the
  socket-activated account service.
- `docs/ws-proxy.md` — the WebSocket-to-TCP tunnel that browser clients use
  in place of raw SMTP/IMAP.
- `docs/admin-bot.md` — Veltar, the chat-driven relay admin bot.

When a feature documented here changes on the server, update the matching
doc in the same change. Docs that drift from the box are worse than none.

## 4. Verify before you claim

Never report a server change as done without: `systemctl is-active` on the
touched units, and a curl against the affected public endpoint. Mail-path
services (postfix, dovecot, the filtermail chain) are restarted only with
explicit reason — a metadata/dict restart is cheap, an IMAP restart drops
client sessions.
