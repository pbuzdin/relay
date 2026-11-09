"""Owner-only invite commands for Veltar (pure logic, no Delta Chat imports).

Proxy tokens are byte-compatible with velta's tools/deploy-ws-proxy.sh bridge.py:
  b64url(json{"v":1,"i":id,"n"?,"e"?,"u"?}) "." b64url(HMAC-SHA256(secret, body))
Relay invites use the existing /i/<token> store of /usr/lib/cgi-bin/invite.py on the relay.
"""
import base64, datetime, fcntl, hashlib, hmac, io, json, os, re, secrets, shlex, sys, time
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

HELP = """Commands (owner only):
/proxy invite NAME [30d|12h|YYYY-MM-DD] [uses N]  WebSocket proxy link + QR
/proxy list
/proxy revoke ID
/pwa invite NAME [r ID] [30d|12h|YYYY-MM-DD] [uses N]  one-click PWA link + QR
/relay invite NAME [30d|YYYY-MM-DD] [uses N]      relay signup link + QR
/relay list
/relay revoke ID
/invite NAME [r ID] [30d|12h|YYYY-MM-DD] [uses N]  signed velta.cc/web link + QR
Expiry defaults to 48h when omitted.
/ai                                         keys and which model answers
/ai grok KEY | /ai glm KEY                  save a Grok (xAI) or z.ai GLM key
/ai use grok|glm                            answer with that model
/ai off                                     stop answering
/ai clear grok|glm                          forget a key
/help"""

class CmdError(ValueError): pass

# ---------- parsing / authorization ----------
def is_authorized(from_id, chat_id, owner_id, owner_chat_id, owner_verified, owner_fp=None, pinned_fp=None):
    """Fail closed: only the owner contact, in the owner's 1:1 chat, and either verified or
    (when a fingerprint is pinned) holding exactly the pinned key. A pin is always enforced if set."""
    if not (bool(owner_id) and from_id == owner_id and chat_id == owner_chat_id): return False
    if pinned_fp:
        return bool(owner_fp) and norm_fp(owner_fp) == norm_fp(pinned_fp)
    return owner_verified is True

def norm_fp(fp):
    return re.sub(r"[^0-9A-F]", "", (fp or "").upper())

def fingerprints(enc_info):
    """All 40-hex OpenPGP fingerprints in core's encryption-info text (groups of 4 separated by spaces)."""
    return [norm_fp(m) for m in re.findall(r"(?:[0-9A-F]{4}\s+){9}[0-9A-F]{4}", enc_info or "")]

SECRET_RE = re.compile(r"([&#?](?:s|i|token|secret|pw|password|invite)=)[^&\s]+", re.I)
AI_KEY_RE = re.compile(r"(?i)(/ai\s+(?:grok|glm|zai|xai)\s+).+")
def redact(s):
    """Hide invite secrets and /ai key arguments before logging or storing."""
    s = SECRET_RE.sub(r"\1REDACTED", str(s))
    return AI_KEY_RE.sub(r"\1REDACTED", s)

def parse_expiry(s, now=None):
    """Same semantics as bridge.py parse_expiry: '' -> 0, Nd/Nh, YYYY-MM-DD (UTC)."""
    s = (s or "").strip(); now = time.time() if now is None else now
    if not s: return 0
    if s[-1] in "dh" and s[:-1].isdigit():
        return int(now + int(s[:-1]) * (86400 if s[-1] == "d" else 3600))
    try: return int(datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())
    except ValueError: raise CmdError(f"bad expiry {s!r} (use 30d, 12h or YYYY-MM-DD)")

EXP_RE = re.compile(r"^(\d+[dh]|\d{4}-\d{2}-\d{2})$")
ID_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")
DEFAULT_EXPIRY_S = 48 * 3600

def _invite_args(args, now, allow_relay=False):
    exp, uses, words, i, relay = 0, 0, [], 0, ""
    while i < len(args):
        if args[i].lower() == "uses" and i + 1 < len(args):
            if not args[i + 1].isdigit() or not 1 <= int(args[i + 1]) <= 1000: raise CmdError("uses must be 1..1000")
            uses = int(args[i + 1]); i += 2; continue
        if allow_relay and args[i].lower() == "r" and i + 1 < len(args):
            relay = args[i + 1]
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?", relay): raise CmdError("bad relay id")
            i += 2; continue
        words.append(args[i]); i += 1
    if len(words) > 1 and EXP_RE.match(words[-1]): exp = parse_expiry(words.pop(), now)
    name = "".join(c for c in " ".join(words) if c.isprintable() and c != "\t")[:64].strip()
    if not name: raise CmdError("NAME is required")
    if exp and exp <= now: raise CmdError("expiry is in the past")
    if not exp: exp = int(now + DEFAULT_EXPIRY_S)
    out = {"name": name, "exp": exp, "uses": uses}
    if allow_relay: out["relay"] = relay
    return out

def parse_command(text, now=None):
    """None for non-commands; dict for commands; raises CmdError on bad usage."""
    now = time.time() if now is None else now
    t = (text or "").strip()
    if not t.startswith("/"): return None
    try: parts = shlex.split(t)
    except ValueError: parts = t.split()
    cmd, args = parts[0].lower(), parts[1:]
    if cmd == "/help": return {"cmd": "help"}
    if cmd == "/invite": return {"cmd": "invite", **_invite_args(args, now, allow_relay=True)}
    if cmd == "/pwa":
        if args and args[0].lower() == "invite": return {"cmd": "pwa_invite", **_invite_args(args[1:], now, allow_relay=True)}
        raise CmdError("usage: /pwa invite NAME [r ID] [30d|12h|YYYY-MM-DD] [uses N]")
    if cmd in ("/proxy", "/relay"): 
        kind = cmd[1:]
        if not args: raise CmdError(f"usage: {cmd} invite|list|revoke")
        sub = args[0].lower()
        if sub == "invite": return {"cmd": f"{kind}_invite", **_invite_args(args[1:], now)}
        if sub == "list" and len(args) == 1: return {"cmd": f"{kind}_list"}
        if sub == "revoke" and len(args) == 2 and ID_RE.match(args[1]): return {"cmd": f"{kind}_revoke", "id": args[1]}
        raise CmdError(f"usage: {cmd} invite NAME [30d|YYYY-MM-DD] [uses N] | {cmd} list | {cmd} revoke ID")
    if cmd == "/ai": return parse_ai(args)
    return {"cmd": "unknown"}

AI_WHICH = {"grok": "grok", "xai": "grok", "glm": "glm", "zai": "glm"}
AI_ENV = {"grok": "XAI_API_KEY", "glm": "ZAI_API_KEY"}
# General API defaults. Coding Plan keys want zai/glm-5.3; say so and switch later.
AI_REF = {"grok": "xai/grok-4.7", "glm": "zai/glm-5.2"}
AI_USAGE = "usage: /ai | /ai grok KEY | /ai glm KEY | /ai use grok|glm | /ai off | /ai clear grok|glm"

def _which(word):
    w = AI_WHICH.get((word or "").lower())
    if not w: raise CmdError(AI_USAGE)
    return w

def parse_ai(args):
    if not args: return {"cmd": "ai_status"}
    sub = args[0].lower()
    if sub == "off" and len(args) == 1: return {"cmd": "ai_off"}
    if sub == "use" and len(args) == 2: return {"cmd": "ai_use", "which": _which(args[1])}
    if sub == "clear" and len(args) == 2: return {"cmd": "ai_clear", "which": _which(args[1])}
    if sub in AI_WHICH and len(args) == 2:
        key = args[1].strip()
        if len(key) < 12 or any(c.isspace() for c in key): raise CmdError("paste the API key as one word, at least 12 characters")
        return {"cmd": "ai_set", "which": _which(sub), "key": key}
    raise CmdError(AI_USAGE)

def ai_path(cfg):
    return cfg.get("ai_env") or "/opt/veltar/ai.env"

def ai_load(path):
    d = {}
    try:
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1); d[k.strip()] = v.strip()
    except OSError: pass
    return d

def ai_save(path, d):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    keys = ("XAI_API_KEY", "ZAI_API_KEY", "AI_MODEL", "AI_REF")
    body = "".join(f"{k}={d[k]}\n" for k in keys if d.get(k))
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(body)
    os.replace(tmp, path); os.chmod(path, 0o600)

def ai_status_text(d):
    def line(label, envk):
        v = d.get(envk) or ""
        return f"{label}: set (…{v[-4:]})" if len(v) >= 4 else f"{label}: not set"
    model = d.get("AI_MODEL") or "off"
    answering = "off" if model == "off" else f"{model} ({d.get('AI_REF') or AI_REF.get(model, '?')})"
    return "\n".join([line("Grok", "XAI_API_KEY"), line("GLM (z.ai)", "ZAI_API_KEY"), f"Answering: {answering}"])

# ---------- proxy tokens (bridge.py compatible) ----------
def b64e(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def load_secret(path):
    key = open(path, "rb").read().strip()
    if len(key) < 32: raise CmdError("proxy secret too short")
    return key

def mint(key, invite_id, name="", exp=0, uses=0):
    p = {"v": 1, "i": invite_id}
    if name: p["n"] = name
    if exp: p["e"] = int(exp)
    if uses: p["u"] = int(uses)   # max devices; bridge.py (velta 0400234+) enforces 1..10000
    body = b64e(json.dumps(p, separators=(",", ":")).encode())
    return body + "." + b64e(hmac.new(key, body.encode(), hashlib.sha256).digest())

class ProxyInvites:
    """cfg: secret, revoked, url, log (veltar-owned tsv), extra_logs (read-only, e.g. root's invites.tsv)."""
    def __init__(self, cfg): self.c = cfg
    def invite(self, name, exp=0, uses=0, pwa=None):
        relay = (pwa or {}).get("relay") or ""
        if relay:
            try: registry = json.load(open(pwa["registry"])).get("relays", {})
            except (OSError, ValueError) as e: raise CmdError(f"cannot read relay registry: {e}")
            if relay not in registry: raise CmdError(f"unknown relay id {relay!r}")
        if pwa and (not pwa.get("key_path") or not os.path.exists(pwa["key_path"])):
            raise CmdError("onboarding signing key is missing")
        iid = secrets.token_hex(6); exp = int(exp or 0)
        tok = mint(load_secret(self.c["secret"]), iid, name, exp, uses)
        # same line format as bridge.py --mint: id<TAB>name<TAB>expiry[<TAB>uses]
        with open(self.c["log"], "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX); f.write(f"{iid}\t{name}\t{exp}" + (f"\t{int(uses)}" if uses else "") + "\n")
        if pwa:
            import pwa_onboarding
            try: registry = json.load(open(pwa["registry"])).get("relays", {})
            except (OSError, ValueError) as e: raise CmdError(f"cannot read relay registry: {e}")
            relays = {relay: registry[relay]} if relay else dict(registry)
            key = pwa_onboarding.load_private_key(pwa["key_path"])
            link = pwa_onboarding.mint_pwa_invite(tok, pwa["proxy"], relays, key, pwa["key_id"], pwa["url"].rstrip("/"))
        else:
            link = "velta://ws?u=" + quote(self.c["url"], safe="") + ("&n=" + quote(name, safe="") if name else "") + "&t=" + tok
        return iid, link
    def _revoked(self):
        try: return {l.strip() for l in open(self.c["revoked"]) if l.strip() and not l.startswith("#")}
        except OSError: return set()
    def list(self, now=None):
        now = time.time() if now is None else now; rev = self._revoked(); rows = []
        for p in [self.c["log"]] + list(self.c.get("extra_logs", [])):
            try: rows += [l.rstrip("\n").split("\t") for l in open(p) if l.strip()]
            except OSError: pass
        out = []
        for r in rows:
            iid, name, exp, uses = (r + ["", "", "0", ""])[:4]; exp = int(exp or 0)
            st = "revoked" if iid in rev else ("expired" if exp and exp <= now else "active")
            when = time.strftime("%Y-%m-%d", time.gmtime(exp)) if exp else "never"
            cap = f"  max {uses} devices" if uses.isdigit() and int(uses) > 0 else ""
            out.append(f"{iid}  {name or '-'}  exp {when}{cap}  {st}")
        return out
    def revoke(self, iid):
        if not ID_RE.match(iid): raise CmdError("bad id")
        if iid in self._revoked(): return False
        # append in place (keeps owner/group/mode; bridge re-reads on mtime change)
        with open(self.c["revoked"], "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX); f.write(iid + "\n")
        return True

# ---------- relay invites (store of /usr/lib/cgi-bin/invite.py) ----------
class RelayInvites:
    """cfg: store, domain. Writes in place under flock exactly like invite.py claim()."""
    def __init__(self, cfg): self.c = cfg
    def _edit(self, fn):
        with open(self.c["store"], "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX); raw = f.read()
            data = json.loads(raw) if raw.strip() else {"invites": {}}
            res = fn(data)
            f.seek(0); f.truncate(); json.dump(data, f, indent=1); f.flush(); os.fsync(f.fileno())
            return res
    def invite(self, name, exp=0, uses=0):
        token = secrets.token_urlsafe(18); h = hashlib.sha256(token.encode()).hexdigest()
        def add(d):
            d.setdefault("invites", {})[h] = {"uses": uses or 1, "expires": int(exp), "revoked": False,
                                             "note": "", "name": name, "created": int(time.time()), "by": "veltar"}
        self._edit(add)
        return h[:8], f"https://{self.c['domain']}/i/{token}"
    def list(self, now=None):
        now = int(time.time() if now is None else now)
        with open(self.c["store"]) as f:
            fcntl.flock(f, fcntl.LOCK_SH); raw = f.read()
        out = []
        for h, inv in (json.loads(raw) if raw.strip() else {"invites": {}})["invites"].items():
            st = "revoked" if inv.get("revoked") else ("expired" if inv.get("expires") and inv["expires"] < now
                 else "used up" if inv.get("uses", 1) <= 0 else f"{inv.get('uses', 1)} left")
            out.append(f"{h[:8]}  {inv.get('name') or inv.get('note') or '-'}  {st}  claimed {len(inv.get('claimed', []))}")
        return out
    def revoke(self, iid):
        def rv(d):
            hits = [h for h in d["invites"] if h.startswith(iid.lower())]
            if len(hits) != 1: raise CmdError("no such id" if not hits else "ambiguous id, give more chars")
            d["invites"][hits[0]]["revoked"] = True
        if len(iid) < 6: raise CmdError("give at least 6 chars of the id")
        self._edit(rv); return True

# ---------- QR ----------
def qr_png(data, path):
    import segno
    segno.make(data, error="m").save(path, kind="png", scale=8, border=4)
    return path

# ---------- dispatcher ----------
def handle(cmd, cfg, tmpdir, now=None):
    """Return list of (text, file_or_None) replies. cfg = veltar config dict."""
    p = cfg.get("proxy_invites") or {}; r = cfg.get("relay_invites") or {}; w = cfg.get("pwa_invites") or {}
    pon, ron = bool(p.get("enabled")), bool(r.get("enabled"))
    c = cmd["cmd"]
    def off(k): return [(f"{k} invites are not enabled on this bot.", None)]
    def qr(link, tag): return qr_png(link, os.path.join(tmpdir, f"{tag}-{secrets.token_hex(4)}.png"))
    def exp_s(e): return time.strftime("%Y-%m-%d", time.gmtime(e)) if e else "never"
    if c == "help": return [(HELP, None)]
    if c == "unknown": return [("Unknown command. /help", None)]
    if c == "ai_status": return [(ai_status_text(ai_load(ai_path(cfg))), None)]
    if c == "ai_off":
        d = ai_load(ai_path(cfg)); d["AI_MODEL"] = "off"; d.pop("AI_REF", None); ai_save(ai_path(cfg), d)
        return [("AI answers off. Keys are kept. /ai use grok or /ai use glm to turn them back on.", None)]
    if c == "ai_clear":
        d = ai_load(ai_path(cfg)); d.pop(AI_ENV[cmd["which"]], None)
        if d.get("AI_MODEL") == cmd["which"]: d["AI_MODEL"] = "off"; d.pop("AI_REF", None)
        ai_save(ai_path(cfg), d)
        return [(f"{cmd['which']} key cleared.\n" + ai_status_text(d), None)]
    if c == "ai_use":
        d = ai_load(ai_path(cfg))
        if not d.get(AI_ENV[cmd["which"]]): raise CmdError(f"no {cmd['which']} key yet. Send /ai {cmd['which']} KEY")
        d["AI_MODEL"] = cmd["which"]; d["AI_REF"] = AI_REF[cmd["which"]]; ai_save(ai_path(cfg), d)
        return [(f"Answering with {d['AI_REF']}.\n" + ai_status_text(d), None)]
    if c == "ai_set":
        d = ai_load(ai_path(cfg)); d[AI_ENV[cmd["which"]]] = cmd["key"]
        if d.get("AI_MODEL") in (None, "", "off"):
            d["AI_MODEL"] = cmd["which"]; d["AI_REF"] = AI_REF[cmd["which"]]
        ai_save(ai_path(cfg), d)
        name = "Grok" if cmd["which"] == "grok" else "GLM"
        return [(f"{name} key saved (…{cmd['key'][-4:]}). Answering with {d.get('AI_REF')}. /ai off stops it.", None)]
    if c.startswith("proxy") and not pon: return off("Proxy")
    if c.startswith("relay") and not ron: return off("Relay")
    if c == "pwa_invite":
        if not pon or not w.get("enabled"): return off("PWA")
        pwa = {"url": w["url"], "registry": w["registry"], "relay": cmd.get("relay") or "",
               "key_path": w.get("key_path"), "key_id": w.get("key_id"), "proxy": w.get("proxy")}
        iid, link = ProxyInvites(p).invite(cmd["name"], cmd["exp"], cmd["uses"], pwa=pwa)
        return [(f"PWA invite for {cmd['name']} (id {iid}, expires {exp_s(cmd['exp'])}"
                 + (f", {cmd['uses']} devices" if cmd["uses"] else "") + f"):\n{link}", qr(link, "pwa"))]
    if c == "proxy_invite":
        iid, link = ProxyInvites(p).invite(cmd["name"], cmd["exp"], cmd["uses"])
        return [(f"Proxy invite for {cmd['name']} (id {iid}, expires {exp_s(cmd['exp'])}"
                 + (f", {cmd['uses']} devices" if cmd["uses"] else "") + f"):\n{link}", qr(link, "proxy"))]
    if c == "proxy_list": return [("\n".join(ProxyInvites(p).list(now)) or "No proxy invites.", None)]
    if c == "proxy_revoke":
        return [(f"Revoked {cmd['id']}." if ProxyInvites(p).revoke(cmd["id"]) else f"{cmd['id']} was already revoked.", None)]
    if c == "relay_invite":
        iid, link = RelayInvites(r).invite(cmd["name"], cmd["exp"], cmd["uses"])
        return [(f"Relay invite for {cmd['name']} (id {iid}, {cmd['uses'] or 1} use(s), expires {exp_s(cmd['exp'])}):\n{link}", qr(link, "relay"))]
    if c == "relay_list": return [("\n".join(RelayInvites(r).list(now)) or "No relay invites.", None)]
    if c == "relay_revoke": RelayInvites(r).revoke(cmd["id"]); return [(f"Revoked relay invite {cmd['id']}.", None)]
    if c == "invite":
        # One link only: the signed PWA invite sets up the proxy and creates the account
        # on a registry relay. Relay-hosted signups stay under /relay invite.
        if not pon or not w.get("enabled"): return off("PWA")
        pwa = {"url": w["url"], "registry": w["registry"], "relay": cmd.get("relay") or "",
               "key_path": w.get("key_path"), "key_id": w.get("key_id"), "proxy": w.get("proxy")}
        pid, pl = ProxyInvites(p).invite(cmd["name"], cmd["exp"], cmd["uses"], pwa=pwa)
        return [(f"Invite for {cmd['name']} (id {pid}, expires {exp_s(cmd['exp'])}"
                 + (f", {cmd['uses']} devices" if cmd["uses"] else "") + f"). Open in a browser or Velta:\n{pl}", None),
                ("PWA QR", qr(pl, "pwa"))]
    return [("Unknown command. /help", None)]

def _demo():
    import shutil, tempfile
    d = tempfile.mkdtemp(); cfg = {"ai_env": os.path.join(d, "ai.env")}; secret = "xai-secret-value-1234"
    try:
        assert parse_command("hello") is None
        assert parse_command("/help")["cmd"] == "help"
        assert parse_command("/invite Ada", now=1_700_000_000)["exp"] == 1_700_000_000 + DEFAULT_EXPIRY_S
        assert parse_command("/proxy list")["cmd"] == "proxy_list"
        assert parse_command("/relay revoke abcdef")["id"] == "abcdef"
        assert redact("/ai grok " + secret) == "/ai grok REDACTED"
        assert secret not in redact("/ai glm " + secret + "\nthanks")
        try: parse_command("/ai grok short"); raise AssertionError("short key accepted")
        except CmdError: pass
        cmd = parse_command("/ai grok " + secret)
        reply = handle(cmd, cfg, d)[0][0]
        assert secret not in reply and "1234" in reply and "/ai off stops it." in reply
        stored = open(cfg["ai_env"]).read()
        assert secret in stored and "AI_REF=xai/grok-4.7" in stored
        status = handle({"cmd": "ai_status"}, cfg, d)[0][0]
        assert secret not in status and "set" in status and "grok-4.7" in status
        try: handle({"cmd": "ai_use", "which": "glm"}, cfg, d); raise AssertionError("glm use without key")
        except CmdError: pass
        handle(parse_command("/ai glm sk-glm-secret-5678"), cfg, d)
        handle({"cmd": "ai_use", "which": "glm"}, cfg, d)
        assert "AI_REF=zai/glm-5.2" in open(cfg["ai_env"]).read()
        handle({"cmd": "ai_off"}, cfg, d)
        assert "AI_MODEL=off" in open(cfg["ai_env"]).read() and "AI_REF=" not in open(cfg["ai_env"]).read()
        handle({"cmd": "ai_clear", "which": "grok"}, cfg, d)
        assert secret not in open(cfg["ai_env"]).read()
        key_path = d + "/proxy-secret"; open(key_path, "wb").write(b"x" * 32)
        registry = d + "/relays.json"; json.dump({"v": 1, "relays": {"one": "one.example.org"}}, open(registry, "w"))
        cmd = parse_command("/pwa invite Ann r one 12h uses 1", now=0)
        assert cmd["relay"] == "one" and cmd["uses"] == 1 and cmd["exp"] == 12 * 3600
        pc = {"secret": key_path, "log": d + "/invites.tsv"}
        try:
            ProxyInvites(pc).invite(cmd["name"], cmd["exp"], cmd["uses"], pwa={"url": "https://velta.cc/web", "registry": registry, "relay": cmd["relay"]})
            raise AssertionError("unsigned pwa invite")
        except CmdError: pass
        # v2 signed
        import pwa_onboarding
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        from urllib.parse import urlsplit, parse_qs
        k = Ed25519PrivateKey.generate(); kp = d + "/ob.pem"
        open(kp, "wb").write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        json.dump({"v": 1, "relays": {"one": "one.example.org", "nine": "nine.testrun.org"}}, open(registry, "w"))
        v2 = {"url": "https://velta.cc/web", "registry": registry, "key_path": kp, "key_id": "test1", "proxy": "wss://p.example.org/vp"}
        for rel, want in (("one", {"one"}), ("", {"one", "nine"})):
            iid, link = ProxyInvites(pc).invite("Ann", 1900000000, 1, pwa={**v2, "relay": rel})
            assert "&r=" not in link and link.startswith("https://velta.cc/web?invite=")
            env = parse_qs(urlsplit(link).query)["invite"][0]; body, sig = env.split(".")
            raw = pwa_onboarding.b64url_decode(body); k.public_key().verify(pwa_onboarding.b64url_decode(sig), raw)
            pl = json.loads(raw); tokp = json.loads(pwa_onboarding.b64url_decode(pl["t"].split(".")[0]))
            assert pl["v"] == 2 and pl["k"] == "test1" and set(pl["r"]) == want and pl["e"] == tokp["e"] == 1900000000
            assert "invite=REDACTED" in redact(link)
        cfg["proxy_invites"] = {**pc, "enabled": True, "url": v2["proxy"]}
        cfg["pwa_invites"] = {**v2, "enabled": True}
        store = d + "/relay-invites.json"; json.dump({"invites": {}}, open(store, "w"))
        cfg["relay_invites"] = {"enabled": True, "store": store, "domain": "signup.example.org"}
        for command, want in (("/invite Ann 1d uses 1", {"one", "nine"}), ("/invite Ann r nine 1d uses 1", {"nine"})):
            replies = handle(parse_command(command), cfg, d)
            text = replies[0][0]
            assert "/i/" not in text and "velta://ws" not in text
            assert replies[-1][0] == "PWA QR"
            link = next(line for line in text.splitlines() if line.startswith("https://velta.cc/web?"))
            env = parse_qs(urlsplit(link).query)["invite"][0]; body, sig = env.split(".")
            raw = pwa_onboarding.b64url_decode(body); k.public_key().verify(pwa_onboarding.b64url_decode(sig), raw)
            assert set(json.loads(raw)["r"]) == want
        cfg["pwa_invites"]["enabled"] = False
        assert "not enabled" in handle(parse_command("/invite Ann"), cfg, d)[0][0]
        assert "velta://ws" in handle(parse_command("/proxy invite Ann"), cfg, d)[0][0]
        cfg["pwa_invites"]["enabled"] = True
        try: ProxyInvites(pc).invite("Ann", pwa={**v2, "relay": "nope"}); raise AssertionError("unknown relay")
        except CmdError: pass
        try:
            ProxyInvites(pc).invite("Ann", pwa={**v2, "key_path": d + "/missing", "relay": "one"})
            raise AssertionError("missing key minted a link")
        except CmdError: pass
        print("ok")
    finally:
        shutil.rmtree(d)

if __name__ == "__main__":
    _demo()
