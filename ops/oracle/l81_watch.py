#!/usr/bin/env python3
"""LEGACIS81 - Surveillance Gmail -> Telegram (serveur Oracle A1).

Aucun secret dans ce fichier : les codes sont lus dans /etc/legacis81/watch.env
(TG_TOKEN, GMAIL_USER, GMAIL_APP_PW, TG_CHAT_ID).

Commandes :
  run      relève Telegram (boutons) puis Gmail (nouveaux emails)  -> toutes les 5 min
  digest   résumé quotidien + signal de vie                         -> 1 fois / jour
  selftest vérifie Gmail et Telegram, envoie un message de test
  chatid   lit le dernier /start reçu par le bot et affiche le chat_id

Principes : lecture seule des emails (BODY.PEEK, rien n'est marqué lu ni supprimé),
aucune donnée client dans Telegram au-delà de l'objet de l'email, libellés Gmail
pour transmettre au RCO (Claude) les demandes à préparer.
"""
import email, email.header, email.utils, imaplib, json, os, sqlite3, sys, time
import urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ENV = "/etc/legacis81/watch.env"
DB = "/var/lib/legacis81-watch/state.db"
LABEL_TODO = "L81-RCO/A-preparer"      # le RCO prépare une réponse
LABEL_LOIC = "L81-RCO/Loic-s-en-occupe"
LABEL_SEEN = "L81-RCO/Vu-par-Oracle"

# (catégorie, important?, mots-clés objet) - testés dans l'ordre
RULES_ETSY = [
    ("VENTE", True, ["you made a sale", "vous avez fait une vente", "vous avez vendu", "congratulations on your", "new order", "nouvelle commande"]),
    ("LITIGE", True, ["case", "dispute", "litige", "a ouvert un cas", "opened a case"]),
    ("MESSAGE", True, ["sent you a message", "vous a envoyé un message", "new message", "nouveau message", "conversation", "a question"]),
    ("ANNULATION", True, ["cancel", "annul"]),
    ("AVIS", False, ["review", "avis"]),
]
RULES_PRINTFUL = [
    ("PROBLEME PRINTFUL", True, ["on hold", "en attente", "action required", "action requise", "failed", "échec", "problem", "problème", "issue", "returned", "retourn", "cancel", "annul", "payment", "paiement"]),
    ("EXPEDITION", False, ["shipped", "expédi", "on its way", "en route", "delivered", "livré"]),
    ("PRINTFUL", False, [""]),
]
SENDERS_WATCH = {"sinden": ("SINDEN (représentant UE)", True)}


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_env():
    cfg = {}
    with open(ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, msgid TEXT UNIQUE, cat TEXT, important INT, subject TEXT, sender TEXT, date TEXT, state TEXT, created TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
    return c


def kv_get(c, k, d=None):
    r = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r[0] if r else d


def kv_set(c, k, v):
    c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v)))
    c.commit()


# ---------------- Telegram ----------------
def tg(cfg, method, **params):
    url = f"https://api.telegram.org/bot{cfg['TG_TOKEN']}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError(f"Telegram {method}: {res}")
    return res["result"]


def send(cfg, text, buttons=None):
    p = {"chat_id": int(cfg["TG_CHAT_ID"]), "text": text[:4000], "disable_web_page_preview": True}
    if buttons:
        p["reply_markup"] = {"inline_keyboard": buttons}
    return tg(cfg, "sendMessage", **p)


# ---------------- Gmail ----------------
def dec(h):
    if not h:
        return ""
    out = []
    for part, cs in email.header.decode_header(h):
        out.append(part.decode(cs or "utf-8", "replace") if isinstance(part, bytes) else part)
    return " ".join("".join(out).split())


def imap(cfg):
    m = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    m.login(cfg["GMAIL_USER"], cfg["GMAIL_APP_PW"])
    return m


def classify(sender, subject):
    s, sub = sender.lower(), subject.lower()
    for key, (cat, imp) in SENDERS_WATCH.items():
        if key in s:
            return cat, imp
    if "etsy" in s:
        for cat, imp, kws in RULES_ETSY:
            if any(k in sub for k in kws):
                return cat, imp
        return None
    if "printful" in s:
        for cat, imp, kws in RULES_PRINTFUL:
            if any(k in sub for k in kws):
                return cat, imp
    return None


def label(m, uid, name):
    try:
        m.create(f'"{name}"')
    except Exception:
        pass
    m.uid("COPY", uid, f'"{name}"')


def check_gmail(cfg, c):
    m = imap(cfg)
    try:
        m.select("INBOX", readonly=False)
        since = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        typ, data = m.uid("SEARCH", None, f'(SINCE "{since}")')
        uids = data[0].split()[-200:]
        new = 0
        for uid in uids:
            typ, d = m.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
            if not d or not d[0]:
                continue
            msg = email.message_from_bytes(d[0][1])
            mid = (msg.get("Message-ID") or f"uid-{uid.decode()}").strip()
            if c.execute("SELECT 1 FROM items WHERE msgid=?", (mid,)).fetchone():
                continue
            sender, subject = dec(msg.get("From")), dec(msg.get("Subject"))
            res = classify(sender, subject)
            if not res:
                c.execute("INSERT INTO items(msgid,cat,important,subject,sender,date,state,created) VALUES(?,?,?,?,?,?,?,?)",
                          (mid, "IGNORE", 0, "", "", "", "ignore", datetime.now(timezone.utc).isoformat()))
                c.commit()
                continue
            cat, imp = res
            c.execute("INSERT INTO items(msgid,cat,important,subject,sender,date,state,created) VALUES(?,?,?,?,?,?,?,?)",
                      (mid, cat, int(imp), subject, email.utils.parseaddr(sender)[1], dec(msg.get("Date")), "new", datetime.now(timezone.utc).isoformat()))
            iid = c.execute("SELECT id FROM items WHERE msgid=?", (mid,)).fetchone()[0]
            c.commit()
            label(m, uid, LABEL_SEEN)
            new += 1
            if imp:
                icon = {"VENTE": "🛍️", "MESSAGE": "💬", "LITIGE": "⚠️", "ANNULATION": "❌", "PROBLEME PRINTFUL": "🚨"}.get(cat, "🔔")
                send(cfg, f"{icon} {cat} — LEGACIS81\n{subject}\n\nQue fait-on ?",
                     [[{"text": "✅ Je m'en occupe", "callback_data": f"own:{iid}"},
                       {"text": "📝 Préparer une réponse", "callback_data": f"draft:{iid}"}]])
                kv_set(c, f"uid:{iid}", uid.decode())
        log(f"gmail ok, {len(uids)} emails lus, {new} nouveaux")
    finally:
        try:
            m.logout()
        except Exception:
            pass


def poll_telegram(cfg, c):
    off = int(kv_get(c, "tg_offset", "0"))
    ups = tg(cfg, "getUpdates", offset=off, timeout=0, allowed_updates=["message", "callback_query"])
    for u in ups:
        kv_set(c, "tg_offset", u["update_id"] + 1)
        if "callback_query" in u:
            q = u["callback_query"]
            if str(q["from"]["id"]) != str(cfg["TG_CHAT_ID"]):
                continue
            act, _, iid = q.get("data", "").partition(":")
            row = c.execute("SELECT subject FROM items WHERE id=?", (iid,)).fetchone()
            uid = kv_get(c, f"uid:{iid}")
            target = LABEL_TODO if act == "draft" else LABEL_LOIC
            try:
                m = imap(cfg); m.select("INBOX")
                if uid:
                    label(m, uid.encode(), target)
                m.logout()
            except Exception as e:
                log("label err", e)
            c.execute("UPDATE items SET state=? WHERE id=?", (act, iid)); c.commit()
            tg(cfg, "answerCallbackQuery", callback_query_id=q["id"], text="Noté ✅")
            if act == "draft":
                send(cfg, f"📝 Transmis au RCO : réponse FR/EN à préparer.\n« {row[0] if row else ''} »\nTu valideras avant tout envoi.")
            else:
                send(cfg, "✅ Noté : tu t'en occupes.")
        elif "message" in u:
            msg = u["message"]
            if str(msg["chat"]["id"]) != str(cfg["TG_CHAT_ID"]):
                continue
            t = (msg.get("text") or "").strip().lower()
            if t in ("/status", "/etat", "/start"):
                n = c.execute("SELECT COUNT(*) FROM items WHERE important=1 AND state='new'").fetchone()[0]
                send(cfg, f"🟢 Surveillance LEGACIS81 active.\nDernière vérification : {kv_get(c,'last_ok','—')}\nAlertes en attente de décision : {n}")


def digest(cfg, c):
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rows = c.execute("SELECT cat, important, subject, state FROM items WHERE created>? AND cat!='IGNORE'", (since,)).fetchall()
    pend = c.execute("SELECT COUNT(*) FROM items WHERE important=1 AND state='new'").fetchone()[0]
    lines = [f"📋 Résumé LEGACIS81 — {datetime.now().strftime('%d/%m/%Y')}"]
    if not rows:
        lines.append("Rien de nouveau ces dernières 24 h.")
    for cat, imp, sub, st in rows[:20]:
        lines.append(f"• {cat} : {sub[:90]}")
    lines.append(f"\nDécisions en attente : {pend}")
    lines.append(f"🟢 Serveur OK — dernière vérification {kv_get(c,'last_ok','—')}")
    send(cfg, "\n".join(lines))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    cfg = load_env()
    c = db()
    if cmd == "chatid":
        ups = tg(cfg, "getUpdates", timeout=0)
        ids = {u["message"]["chat"]["id"]: u["message"]["from"].get("first_name", "") for u in ups if "message" in u}
        print(json.dumps(ids))
        return
    if cmd == "selftest":
        me = tg(cfg, "getMe"); log("telegram ok:", me.get("username"))
        m = imap(cfg); m.select("INBOX", readonly=True); m.logout(); log("gmail ok")
        send(cfg, "✅ LEGACIS81 — Le serveur Oracle est connecté.\nJe surveille Etsy et Printful toutes les 5 minutes et je t'écris ici seulement si c'est important.\nEnvoie /status pour vérifier que je suis en ligne.")
        return
    if cmd == "digest":
        digest(cfg, c); return
    errs = []
    try:
        poll_telegram(cfg, c)
    except Exception as e:
        errs.append(f"telegram: {e}")
    try:
        check_gmail(cfg, c)
        kv_set(c, "last_ok", datetime.now().strftime("%d/%m %H:%M"))
        kv_set(c, "fails", 0)
    except Exception as e:
        errs.append(f"gmail: {e}")
        f = int(kv_get(c, "fails", "0")) + 1
        kv_set(c, "fails", f)
        if f == 3:
            try:
                send(cfg, f"⚠️ LEGACIS81 : la lecture Gmail échoue depuis 15 min.\nDétail technique : {str(e)[:200]}")
            except Exception:
                pass
    if errs:
        log("ERREURS", errs)
        sys.exit(1)


if __name__ == "__main__":
    main()
