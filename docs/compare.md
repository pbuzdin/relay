# Upstream chatmail vs the Velta overlay

What stock `chatmail` main provides, what the Velta overlay adds, and where
each piece is documented. "Overlay" means the hand-applied delta deployed on
the production relay; the long-term goal is to move every overlay row into
cmdeploy templates (see the backlog in `VELTA-DEPLOY.md`).

| Capability | Upstream chatmail main | Velta overlay | Docs |
|---|---|---|---|
| Account creation | Open signup via `/new`, rate-limited | **Invite-only**: tokens with uses/expiry, claim endpoint, socket-activated `mkaccount` service (no always-on privileged listener) | [invites.md](invites.md) |
| Signup gating | None (self-service) | Closed; accounts minted only through a valid token | [invites.md](invites.md) |
| WebSocket mail tunnel | None | **C3 tunnel**: WS-to-TCP bridges for IMAP/SMTP plus generic `/tcp/{host}/{port}` and `/dns` resolvers, origin allowlist for browsers | [ws-proxy.md](ws-proxy.md) |
| Browser/PWA hosting | None | Static PWA + assets under the relay origin, same-origin WS endpoints | VELTA-DEPLOY.md §3 |
| filtermail | Outgoing spam filter | Outgoing + **incoming** + **transport** split as three services | VELTA-DEPLOY.md §4 |
| Inbound HTTPS federation | None | `mxdeliv` receiver: DKIM-aligned, E2EE-enforced, envelope auth headers | VELTA-DEPLOY.md §4 |
| iroh relay | Optional single 0.35 relay | **Dual-line**: 0.35 (derp) for current core clients incl. Delta Chat, 1.3.0 `exp/iroh-1` for the iroh 1.x future; both advertised via `irohrelay` / `irohrelay1` metadata | VELTA-DEPLOY.md §5 |
| TURN / calls | coturn deployment + metadata | Same, wired into the metadata annotations | upstream |
| Metadata annotations | `chatmail-metadata` dict proxy (`appversions`, `turn`, …) | Same, plus iroh lines kept filled (empty key = feature off — see invites/ws docs for the gotcha) | upstream |
| Web landing page | Static landing | Landing + privacy/legal pages fed from config | upstream |
| Relay administration | SSH only | **Veltar bot**: chat-driven admin on the relay's own DC account (invites, status, messaging) | [admin-bot.md](admin-bot.md) |
| Ops scripts | Manual | Deploy/diag/e2e/firewall-audit scripts + banner/crash tests | VELTA-DEPLOY.md |

## Deployment postures

- **Upstream**: `cmdeploy run` gives the left column.
- **Overlay**: `cmdeploy run` first, then the overlay steps in
  `VELTA-DEPLOY.md` (§ order matters: DNS, TLS, mail path, then services).
  Each deep-dive doc lists its own restarts and verification curls.
