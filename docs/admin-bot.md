# Veltar — the relay admin bot

Veltar is a Delta Chat bot running on the relay's own DC account. It turns
relay administration into chatting: mint invites, check status, relay
messages — from any admin's phone, no SSH.

## Surface

```text
veltar serve            # run the bot (systemd unit: veltar.service)
veltar send TEXT [--file PATH]   # queue a message to the owner (use - for stdin)
veltar inbox [--since TS] [--all]  # dump recent inbound messages as JSON lines
veltar status           # print the bot's config (contains secrets; root only)
```

`serve` is what the systemd unit runs: an unprivileged `veltar` user with a
venv under `/opt/veltar`, handling inbound messages and replying. Invite
minting (`invites.py`) reuses the same token store and rules as the CLI
(see [invites.md](invites.md)). The bot is a second front end, not a second
source of truth.

The source is in [`veltar/`](../veltar/) with deploy steps in its README.

## What it can do

### Owner and access

- On first start Veltar creates its account (from `creds.json` or the signup
  QR in `relay_invite.txt`) and writes its own invite to `invite.txt`.
- The first contact who scans that invite becomes the **owner**. Later joiners
  are logged and ignored.
- Commands are accepted only from the owner, only in the owner's 1:1 chat, and
  only when the owner is verified or holds the key pinned in
  `owner_fingerprint`. Anything else gets no reply at all, so the bot never
  auto-replies to strangers.
- Every inbound message is recorded in `inbox.jsonl` with invite secrets and
  API keys redacted. Agents on the server read it with `veltar inbox`.
- `veltar send` lets server-side tools and agents message the owner (and only
  the owner) through an outbox the daemon drains every second.

### Chat commands

| Command | What it does |
|---|---|
| `/invite NAME [r ID] [30d\|12h\|YYYY-MM-DD] [uses N]` | One-stop invite: a single signed v2 velta.cc/web link (plus QR) that opens Velta, sets up the WebSocket proxy and creates an account on a relay from the registry. `r ID` pins one relay. For a signup on this relay itself, use `/relay invite`. |
| `/pwa invite NAME [r ID] [expiry] [uses N]` | Only the signed v2 PWA link and its QR. |
| `/proxy invite NAME [expiry] [uses N]` | A raw `velta://ws` proxy link and QR for the Velta apps. |
| `/proxy list` | Lists proxy invites with expiry, device cap and status. |
| `/proxy revoke ID` | Revokes a proxy invite. The bridge picks it up without a restart. |
| `/relay invite NAME [expiry] [uses N]` | A relay signup link (`/i/<token>`) and QR. |
| `/relay list` | Lists relay invites with uses left and claim count. |
| `/relay revoke ID` | Revokes a relay invite (6+ characters of its id). |
| `/ai` | Shows which AI keys are saved (last 4 characters only) and which model is set to answer. |
| `/ai grok KEY`, `/ai glm KEY` | Saves an xAI Grok or z.ai GLM API key to `ai.env` (mode 600). |
| `/ai use grok\|glm`, `/ai off`, `/ai clear grok\|glm` | Picks the answering model, turns answers off, or forgets a key. |
| `/help` | Lists the commands. |

Notes:

- `r ID` limits a PWA invite to one relay from the shared registry
  (`/etc/velta-ws-proxy/relays.json`). Without it the invite lists every
  approved relay and the PWA picks the fastest one that responds.
- `uses N` (1 to 1000) caps devices for proxy and PWA invites and uses for
  relay invites.
- Expiry is UTC. Omitting it lasts 48 hours. Pass `30d`, `12h`, or `YYYY-MM-DD` to override.
- `/ai` only stores keys and the model choice in `ai.env`. Veltar itself does
  not call any model; a separate agent on the server reads that file and
  answers through `veltar send`.

## PWA invitation contract

`/pwa invite NAME [r ID] [30d|12h|YYYY-MM-DD] [uses N]` emits a v2
self-contained Velta onboarding link. Veltar keeps the existing HMAC proxy
token as the proxy's bearer credential, then signs an Ed25519 envelope
containing that token, the full proxy URL, approved relay IDs and hostnames,
the key ID, and exactly the same expiry. The URL contains the encoded payload
and detached signature; it has no unsigned `r` query parameter and requires no
public `onboarding.json` registry.

The Velta repository's `scripts/relay-invite/pwa_onboarding.py` is the reference
signer. The deployment-specific bot should call `mint_pwa_invite()` after
minting its normal proxy token. With `r ID`, include only that requested relay;
without it, include the approved candidates for automatic fastest-responsive
selection. Store the Ed25519 private key with the bot's other private
configuration, and give the PWA only the corresponding public verification key
through its `--onboarding-keys` build option.

Base64url encoding is not encryption or authentication. The PWA must verify
the Ed25519 signature before installing a proxy or trusting a relay hostname.
Invite recipients can decode the hostnames, and the created account address
reveals the relay domain. Real hostnames and private keys must never enter
repository content, tests, documentation, or static PWA configuration.

A missing Ed25519 key refuses `/invite` and `/pwa invite`. The bot does not
fall back to an unsigned link. Legacy bare-HMAC links with an unsigned `r`
and same-origin registry remain supported for invitations already issued.

## Configuration

`/opt/veltar/config.json` holds the bot account's credentials and settings
([`veltar/config.example.json`](../veltar/config.example.json) shows every key).
It is **never committed, never logged, never backed up with the web root** —
the bot account is an admin identity; its credentials are a root-equivalent
key for everything the bot can do.

## Ops

- Runs as its own user, venv-isolated; logs to its own file, spool under
  `/opt/veltar`.
- The bot only acts on messages from configured admin addresses; unknown
  senders get nothing.
- Source is in [`veltar/`](../veltar/). Hostnames, keys, account
  credentials and the owner's address live only in the deployment's
  `config.json`, `creds.json` and `relay_invite.txt`, never in the repo.

## Extending

New bot commands should delegate to the same helpers the CLI uses (token
store, status collectors) so the CLI and the bot can never disagree about
state. Anything privileged stays behind the socket-activated services the
bot calls — the bot process itself keeps no root.
