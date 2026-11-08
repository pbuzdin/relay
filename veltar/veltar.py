#!/opt/veltar/venv/bin/python
"""Veltar: Delta Chat bot that lets agents message the owner only."""
import argparse, json, os, sys, time, threading, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import invites
from deltachat_rpc_client import DeltaChat, Rpc
from deltachat_rpc_client.const import EventType
BASE = os.environ.get("VELTAR_HOME", "/opt/veltar"); DATA = f"{BASE}/data"; CFG = f"{BASE}/config.json"
INBOX = f"{BASE}/inbox.jsonl"; OUTBOX = f"{BASE}/outbox"; LOG = f"{BASE}/veltar.log"
# Signup QR for the bot's own account, e.g. "dcaccount:https://relay.example.org/new".
RELAY_QR = open(f"{BASE}/relay_invite.txt").read().strip() if os.path.exists(f"{BASE}/relay_invite.txt") else ""

def load_cfg():
    try: return json.load(open(CFG))
    except FileNotFoundError: return {}
def save_cfg(c):
    json.dump(c, open(CFG + ".tmp", "w"), indent=1); os.replace(CFG + ".tmp", CFG)
def log(*a):
    with open(LOG, "a") as f: print(time.strftime("%F %T"), *(invites.redact(x) for x in a), file=f, flush=True)

def get_account(dc):
    accs = dc.get_all_accounts()
    acc = accs[0] if accs else dc.add_account()
    if not acc.is_configured():
        acc.set_config("bot", "1"); acc.set_config("displayname", "Veltar")
        cf = f"{BASE}/creds.json"
        if os.path.exists(cf):
            c = json.load(open(cf)); acc.add_or_update_transport({"addr": c["email"], "password": c["password"]})
        else:
            if not RELAY_QR: sys.exit("veltar: put a dcaccount: QR in relay_invite.txt or creds.json first")
            acc.add_transport_from_qr(RELAY_QR)
    acc.set_config("bot", "1"); acc.set_config("displayname", "Veltar")
    av = f"{BASE}/avatar.jpg"
    if os.path.exists(av) and not acc.get_config("selfavatar"): acc.set_avatar(av)
    return acc

def setup(acc):
    c = load_cfg(); c["addr"] = acc.get_config("configured_addr"); save_cfg(c)
    qr = acc.get_qr_code(); open(f"{BASE}/invite.txt", "w").write(qr + "\n")
    return qr

def outbox_loop(acc):
    while True:
        for n in sorted(os.listdir(OUTBOX)):
            if not n.endswith(".json"): continue
            p = os.path.join(OUTBOX, n)
            try:
                job = json.load(open(p)); owner = load_cfg().get("owner_contact_id")
                if not owner: log("drop: no owner", n)
                else:
                    chat = acc.get_contact_by_id(owner).create_chat()
                    chat.send_message(text=job.get("text") or None, file=job.get("file"))
                    log("sent to owner", n)
            except Exception as e: log("send error", n, repr(e))
            os.remove(p)
        time.sleep(1)

def serve():
    with Rpc(accounts_dir=DATA) as rpc:
        dc = DeltaChat(rpc); acc = get_account(dc); qr = setup(acc)
        acc.start_io(); log("serving as", acc.get_config("configured_addr"), qr)
        o = load_cfg().get("owner_contact_id")
        if o: log("owner key pin", "match" if invites.norm_fp(owner_fingerprint(acc, acc.get_contact_by_id(o)) or "x")
                  == invites.norm_fp(load_cfg().get("owner_fingerprint") or "y") else "MISMATCH/unset")
        threading.Thread(target=outbox_loop, args=(acc,), daemon=True).start()
        while True:
            ev = acc.wait_for_event()
            if ev.kind == EventType.SECUREJOIN_INVITER_PROGRESS and ev.progress == 1000:
                c = load_cfg()
                if not c.get("owner_contact_id"):
                    c["owner_contact_id"] = ev.contact_id
                    c["owner_addr"] = acc.get_contact_by_id(ev.contact_id).get_snapshot().address
                    save_cfg(c); log("owner set", ev.contact_id, c["owner_addr"])
                elif c.get("owner_contact_id") != ev.contact_id: log("non-owner joined", ev.contact_id)
            elif ev.kind == EventType.INCOMING_MSG:
                s = acc.get_message_by_id(ev.msg_id).get_snapshot()
                owner = load_cfg().get("owner_contact_id")
                rec = {"ts": s.timestamp, "chat_id": s.chat_id, "from": s.sender.get_snapshot().address,
                       "from_owner": s.from_id == owner, "text": invites.redact(s.text or ""), "file": s.file}
                with open(INBOX, "a") as f: f.write(json.dumps(rec, default=str) + "\n")
                acc.get_message_by_id(ev.msg_id).mark_seen()
                try: maybe_command(acc, s, owner)
                except Exception as e: log("command error", repr(e))
            elif ev.kind in (EventType.ERROR, EventType.WARNING):
                log(ev.kind, ev.msg)

def owner_fingerprint(acc, contact):
    """Contact's current key fingerprint (the one in encryption info that is not our own); None if unknown."""
    try:
        own = invites.norm_fp(acc.get_qr_code().split("#", 1)[1].split("&", 1)[0])
        fps = [f for f in invites.fingerprints(contact.get_encryption_info()) if f != own]
        return fps[0] if len(fps) == 1 else None
    except Exception: return None

def maybe_command(acc, s, owner):
    """Owner-only, verified-only, owner's 1:1 chat only. Anything else: silence (never auto-reply)."""
    if not owner or s.from_id != owner or not (s.text or "").startswith("/"): return
    contact = acc.get_contact_by_id(owner); chat = contact.create_chat()
    verified = getattr(contact.get_snapshot(), "is_verified", False)
    if not invites.is_authorized(s.from_id, s.chat_id, owner, chat.id, verified,
                                 owner_fingerprint(acc, contact), load_cfg().get("owner_fingerprint")):
        log("command ignored (not authorized)", s.chat_id); return
    try: cmd = invites.parse_command(s.text)
    except invites.CmdError as e: chat.send_message(text=str(e)); return
    if cmd is None: return
    log("command", cmd["cmd"])
    try: replies = invites.handle(cmd, load_cfg(), f"{BASE}/spool")
    except invites.CmdError as e: replies = [(str(e), None)]
    except OSError as e: replies = [(f"error: {e.strerror} ({e.filename})", None)]
    for text, f in replies:
        chat.send_message(text=text or None, file=f)
        if f:
            try: os.remove(f)  # core copied it into its blobdir
            except OSError: pass

def send(text, file):
    if not load_cfg().get("owner_contact_id"): sys.exit("error: no owner set yet (nobody joined via invite)")
    if file: file = os.path.abspath(file); assert os.path.exists(file), "file missing"
    p = os.path.join(OUTBOX, f"{time.time():.6f}-{uuid.uuid4().hex[:6]}")
    json.dump({"text": text, "file": file}, open(p + ".tmp", "w")); os.replace(p + ".tmp", p + ".json")
    print("queued (daemon delivers to owner within ~1s)")

def inbox(since, all_):
    if not os.path.exists(INBOX): return
    for l in open(INBOX):
        r = json.loads(l)
        if r["ts"] > since and (all_ or r["from_owner"]): print(json.dumps(r, ensure_ascii=False))

ap = argparse.ArgumentParser(prog="veltar"); sp = ap.add_subparsers(dest="cmd", required=True)
sp.add_parser("serve"); s = sp.add_parser("send"); s.add_argument("text", nargs="?", default="")
s.add_argument("--file"); i = sp.add_parser("inbox"); i.add_argument("--since", type=float, default=0)
i.add_argument("--all", action="store_true", help="include non-owner senders")
sp.add_parser("status")
a = ap.parse_args()
if a.cmd == "serve": serve()
elif a.cmd == "send":
    send(sys.stdin.read() if a.text == "-" else a.text, a.file)
elif a.cmd == "inbox": inbox(a.since, a.all)
else: print(json.dumps(load_cfg(), indent=1))
