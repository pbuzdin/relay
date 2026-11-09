# Veltar

Veltar is the relay's admin bot: a Delta Chat bot that lets one owner mint
and revoke invites from a chat. See [docs/admin-bot.md](../docs/admin-bot.md)
for what it can do and how it is secured.

## Files

- `veltar.py`: the daemon and its CLI (`serve`, `send`, `inbox`, `status`).
- `invites.py`: command parsing and invite logic, with no Delta Chat imports.
  Run `python invites.py` for its self-test.
- `pwa_onboarding.py`: signs v2 Velta PWA invites (Ed25519). It also works
  as a CLI: `keygen`, `public`, `mint`.
- `config.example.json`: copy to `config.json` and fill in your values.
- `veltar.service`: the systemd unit.

## Deploy

```sh
useradd --system --home /opt/veltar --shell /usr/sbin/nologin veltar
install -d -o veltar -g veltar /opt/veltar /opt/veltar/outbox /opt/veltar/spool
cp veltar.py invites.py pwa_onboarding.py avatar.png /opt/veltar/
cp config.example.json /opt/veltar/config.json   # then edit it
echo 'dcaccount:https://relay.example.org/new' > /opt/veltar/relay_invite.txt
python3 -m venv /opt/veltar/venv
/opt/veltar/venv/bin/pip install -r requirements.txt
# signing key for v2 PWA invites; prints the public key for the PWA build
/opt/veltar/venv/bin/python /opt/veltar/pwa_onboarding.py keygen veltar1 \
  --private-key /opt/veltar/data/onboarding-ed25519.pem
chown -R veltar:veltar /opt/veltar
cp veltar.service /etc/systemd/system/ && systemctl enable --now veltar
```

On first start Veltar writes its own invite to `/opt/veltar/invite.txt`.
The first person who scans it becomes the owner. Pass the printed public key
to the Velta PWA build with `--onboarding-keys`.

An omitted invite expiry is 48 hours. `/invite` and `/pwa invite` refuse to
mint when the Ed25519 key file is missing.

Never commit `config.json`, `creds.json`, `ai.env`, `data/` or the signing
key. The `.gitignore` here already excludes them.
