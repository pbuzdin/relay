# Veltar — the relay admin bot

Veltar is a Delta Chat bot running on the relay's own DC account. It turns
relay administration into chatting: mint invites, check status, relay
messages — from any admin's phone, no SSH.

## Surface

```text
veltar serve            # run the bot (systemd unit: veltar.service)
veltar send <addr> ...  # send a message from the bot account
veltar inbox            # dump recent inbound messages
veltar status           # relay status snapshot
```

`serve` is what the systemd unit runs: an unprivileged `veltar` user with a
venv under `/opt/veltar`, handling inbound messages and replying. Invite
minting (`invites.py`) reuses the same token store and rules as the CLI
(see [invites.md](invites.md)) — the bot is a second front end, not a second
source of truth.

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

Legacy bare-HMAC links with an unsigned `r` and same-origin registry remain
supported for already issued invitations; new bot output should be v2.

## Configuration

`/opt/veltar/config.json` holds the bot account's credentials and settings.
It is **never committed, never logged, never backed up with the web root** —
the bot account is an admin identity; its credentials are a root-equivalent
key for everything the bot can do.

## Ops

- Runs as its own user, venv-isolated; logs to its own file, spool under
  `/opt/veltar`.
- The bot only acts on messages from configured admin addresses; unknown
  senders get nothing.
- Source lives outside this repository (it contains deployment-specific
  wiring); this doc covers the contract, not the code.

## Extending

New bot commands should delegate to the same helpers the CLI uses (token
store, status collectors) so the CLI and the bot can never disagree about
state. Anything privileged stays behind the socket-activated services the
bot calls — the bot process itself keeps no root.
