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
