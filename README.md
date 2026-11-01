
# Chatmail relays for end-to-end encrypted email

Chatmail relay servers are interoperable Mail Transport Agents (MTAs) designed for:

-  **Zero State:** no private data or metadata collected, messages are auto-deleted, low disk usage

-  **Instant/Realtime:** sub-second message delivery, realtime P2P
   streaming, privacy-preserving Push Notifications for Apple, Google, and Huawei;

-  **Security Enforcement**: Only connections with strict TLS are accepted;
   all messages must be correctly signed with DKIM and OpenPGP-encrypted with minimized metadata.
   There are experimental exceptions for no-DNS relays,
   which are allowed use self-signed TLS certificates
   and which do not need to DKIM-sign their messages.
   Unencrypted messages are allowed in neither case.

-  **Reliable Federation and Decentralization:** No spam or IP reputation checks, federating
   depends on established IETF standards and protocols.

This repository contains everything needed to setup a ready-to-use chatmail relay on an ssh-reachable host.
For getting started and more information please refer to the web version of this repositories' documentation at

[https://chatmail.at/doc/relay](https://chatmail.at/doc/relay)

## Velta relay overlay

This fork tracks upstream and documents the overlay our production relay
runs on top of stock chatmail: invite-only signup, a WebSocket-to-TCP
tunnel for browser clients, a dual-line iroh relay, inbound HTTPS
federation, and a chat-driven admin bot.

- Start at [VELTA-DEPLOY.md](VELTA-DEPLOY.md) — the overlay index,
  hosting prerequisites, and the deploy checklist.
- [docs/compare.md](docs/compare.md) — capability table, upstream vs overlay.
- [docs/invites.md](docs/invites.md) · [docs/ws-proxy.md](docs/ws-proxy.md) ·
  [docs/admin-bot.md](docs/admin-bot.md) — per-feature deep-dives.

The overlay is hand-applied on the server today; backporting it into the
`cmdeploy` templates is the tracked TODO. Agents editing this repo: read
[AGENTS.md](AGENTS.md) first.

