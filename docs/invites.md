# Invite-only signup

The overlay replaces open `/new` signup with token-gated account creation.
Nothing on the box creates an account without a valid invite.

## Pieces

- **Token store** — a JSON store (root:deploy-group readable) of minted
  invites: token, uses left, expiry, note.
- **Landing page** — `GET /i/<token>` renders a greeting page; the invite
  deep-links into the app (`velta://` / PWA URL).
- **Claim endpoint** — `GET /i/claim?t=<token>` (CGI). POST bodies are
  unreliable behind this CGI setup by design — the claim is idempotent from
  the app side.
- **`velta-mkaccount@.socket`** — socket-activated per-connection account
  service. No privileged daemon runs between signups; systemd spawns it per
  claim, it mints the account through the chatmaild path, and exits.

## Minting

```sh
invite-tool.py add [uses] [days] [note]   # mint; note is free-form
invite-tool.py list                       # outstanding invites
invite-tool.py revoke <token>             # kill a token
```

The **Veltar bot** (see [admin-bot.md](admin-bot.md)) wraps the same
commands over Delta Chat: an admin messages the bot, the bot mints and
returns the link.

## Token shape

- `uses` — how many accounts the token can create (1 for personal).
- `days` — validity window from minting. Omitted days is 2 (48 hours); `0` does not expire.
- The token itself is the secret: treat links like passwords. They appear
  nowhere in logs, docs, or this repository.

## Security notes

- The claim endpoint is the only unauthenticated write path on the box;
  it is rate-limited at the web tier and can only create a normal account.
- The token store must never be world-readable, and tokens never go into
  backups of the web root.
- Revoking a token does not delete accounts already created with it.
