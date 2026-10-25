import re, hashlib
from .util import pick

PHONE_RX = re.compile(r"\+?\d[\d\s().-]{6,}\d")
SKIP_HDR = ("field", "type", "action", "column", "attr", "status", "source", "reason", "actor", "time", "_at",
            "date", "note", "system", "operation")
TAKE_HDR = ("email", "phone", "name", "old_value", "new_value", "value", "hash", "mobile")
STOP = {"active", "deleted", "pending", "inactive", "suspended", "closed", "true", "false", "none",
        "null", "verified", "email", "phone", "name"}
TS_RX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def kind_of(v):
    if "@" in v:
        return "email"
    if re.fullmatch(r"[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64}", v.lower()):
        return "hash"
    if len(re.sub(r"\D", "", v)) >= 8 and re.fullmatch(r"\+?[\d\s().-]+", v):
        return "phone"
    return "name"


def resolve(email, ident, audit):
    """Closure over identities + audit log: every email/phone/name/hash ever tied to the user."""
    ids, uids = {email.strip().lower()}, set()
    frames = []
    for f in (ident, audit):
        if f is None or f.empty:
            continue
        ucol = pick(f, "user_id")
        fcol = pick(f, "field", "attribute")
        rows = f.to_dict("records")
        idx, byuid = {}, {}
        for i, r in enumerate(rows):
            for v in r.values():
                v = str(v).strip().lower()
                if v:
                    idx.setdefault(v, []).append(i)
            if ucol and r[ucol]:
                byuid.setdefault(r[ucol], []).append(i)
        frames.append((rows, ucol, fcol, idx, byuid))
    for _ in range(8):
        n = (len(ids), len(uids))
        for rows, ucol, fcol, idx, byuid in frames:
            pos = set()
            for v in ids:
                pos |= set(idx.get(v, []))
            for u in uids:
                pos |= set(byuid.get(u, []))
            for i in pos:
                r = rows[i]
                if ucol and r[ucol]:
                    uids.add(r[ucol])
                field_ok = True
                if fcol:
                    field_ok = any(k in str(r[fcol]).lower() for k in ("email", "phone", "name", "mobile", "hash"))
                for c, v in r.items():
                    v, cl = str(v).strip(), c.lower()
                    if not v or len(v) < 4 or c == ucol or TS_RX.match(v) or v.lower() in STOP:
                        continue
                    if any(k in cl for k in SKIP_HDR) or not any(k in cl for k in TAKE_HDR):
                        continue
                    if cl in ("old_value", "new_value", "value") and not field_ok:
                        continue
                    ids.add(v.lower())
        if n == (len(ids), len(uids)):
            break
    for e in [i for i in ids if "@" in i]:
        for h in (hashlib.md5, hashlib.sha1, hashlib.sha256):
            ids.add(h(e.encode()).hexdigest())
    return {"identifiers": ids, "user_ids": uids}


class Matcher:
    def __init__(self, res):
        vals = sorted({v for v in res["identifiers"] if len(v) >= 4}, key=len, reverse=True)
        self.rx = re.compile("|".join(re.escape(v) for v in vals), re.I) if vals else None
        self.phones = {re.sub(r"\D", "", v) for v in vals if kind_of(v) == "phone"}
        u = sorted(res["user_ids"], key=len, reverse=True)
        self.urx = (re.compile("|".join(r"(?<![A-Za-z0-9])" + re.escape(x) + r"(?![A-Za-z0-9])" for x in u))
                    if u else None)

    def find(self, text):
        out = {m.lower() for m in self.rx.findall(text)} if self.rx else set()
        if self.phones:
            for m in PHONE_RX.findall(text):
                d = re.sub(r"\D", "", m)
                if d in self.phones:
                    out.add(d)
        return out

    def has_uid(self, text):
        return bool(self.urx and self.urx.search(text))
