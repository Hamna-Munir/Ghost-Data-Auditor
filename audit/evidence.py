"""Parse every evidence file ONCE into observations: (resource, system, time, state, text)."""
import re, json, sqlite3, subprocess
from pathlib import Path
from .util import pick, ts
from .activity import resources

KV_RX = re.compile(r'(\w+)=("[^"]*"|\S+)')
TS_RX = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b")
STATE_RX = re.compile(r"\b(NOT_FOUND|ABSENT|DELETED|REMOVED|IDENTIFIABLE|PRESENT|ANONYMIZED|REDACTED|ACTIVE|BLOCKED|ENABLED|DISABLED|FOUND)\b", re.I)
STATE_MAP = {"NOT_FOUND": "ABSENT", "ABSENT": "ABSENT", "DELETED": "ABSENT", "REMOVED": "ABSENT", "IDENTIFIABLE": "PRESENT",
             "PRESENT": "PRESENT", "FOUND": "PRESENT", "ANONYMIZED": "ANONYMIZED", "REDACTED": "REDACTED",
             "ACTIVE": "ACTIVE", "BLOCKED": "BLOCKED", "ENABLED": "ENABLED", "DISABLED": "DISABLED"}
RESULT_MAP = {"hit": "PRESENT", "found": "PRESENT", "miss": "ABSENT", "not_found": "ABSENT", "deleted": "ABSENT"}


class EvidenceStore:
    def __init__(self, ddir, manifest, llm=None, systems=(), categories=()):
        self.d, self.llm, self.obs, self.unread, self.by_res = Path(ddir), llm, [], [], {}
        self.systems = sorted(systems, key=len, reverse=True)
        self.cat_rx = re.compile(r"\b(" + "|".join(map(re.escape, categories)) + r")\b") if categories else None
        if manifest is not None and not manifest.empty:
            fc, pc = pick(manifest, "file_id", "evidence_id", "id"), pick(manifest, "file_path", "path", "filename")
            tc = pick(manifest, "captured_at", "snapshot", "timestamp")
            for r in manifest.to_dict("records"):
                p, fid = self._find(r.get(pc, "")), r.get(fc, "")
                if not p:
                    self.unread.append(f"{fid}: file not found")
                    continue
                try:
                    self._parse(p, fid, ts(r.get(tc)) if tc else None)
                except Exception as e:
                    self.unread.append(f"{fid}: {e!r}")
        for o in self.obs:
            self.by_res.setdefault(o["res"], []).append(o)

    def _find(self, rel):
        for c in (self.d / rel, self.d / "evidence" / rel, self.d / "evidence" / Path(rel).name):
            if rel and c.is_file():
                return c
        hits = list(self.d.rglob(Path(rel).name)) if rel else []
        return hits[0] if hits else None

    # ------------------------------------------------------------------ dispatch
    def _parse(self, p, fid, t0):
        s = p.suffix.lower()
        if s == ".sql":
            return self._sql(p.read_text(errors="ignore"), fid, t0)
        if s == ".json":
            return self._walk(json.loads(p.read_text(errors="ignore")), fid, dict(t=t0))
        if s == ".pdf":
            return self._lines(self._pdf(p), fid, t0)
        if s in (".png", ".jpg", ".jpeg", ".webp"):
            if self.llm is not None and self.llm.enabled:
                return self._lines(self.llm.describe_image(p, case_id="evidence:" + fid), fid, t0)
            self.unread.append(f"{fid}: image skipped (enable Groq vision)")
            return
        self._lines(p.read_text(errors="ignore"), fid, t0)

    def _pdf(self, p):
        try:
            return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=60).stdout
        except Exception:
            from pypdf import PdfReader
            return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)

    def _add(self, **o):
        o.setdefault("link_text", o["text"])
        self.obs.append(o)

    # ------------------------------------------------------------------ structured
    def _record(self, fid, t, system, coll, rec, table=""):
        res = str(rec.get("resource_id") or "")
        if res:
            text = json.dumps(rec, ensure_ascii=False)
            self._add(file_id=fid, t=t, system=system, res=res, coll=coll, kind="record", state="PRESENT",
                      text=text, hint="", table=table)

    def _sql(self, txt, fid, t0):
        m = re.search(r"Captured at:\s*(\S+)", txt)
        t = ts(m.group(1)) if m else t0
        con = sqlite3.connect(":memory:")
        con.executescript(txt)
        for (tbl,) in con.execute("select name from sqlite_master where type='table'").fetchall():
            cur = con.execute(f'select * from "{tbl}"')
            cols = [c[0] for c in cur.description]
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                rec = {}
                if d.get("record_json"):
                    try:
                        rec = json.loads(d["record_json"])
                    except Exception:
                        pass
                rec = {**{k: v for k, v in d.items() if k != "record_json"}, **rec}
                self._record(fid, t, d.get("origin_system") or rec.get("data_store") or tbl,
                             d.get("collection_name") or tbl, rec, tbl)

    def _walk(self, o, fid, ctx):
        if isinstance(o, list):
            for x in o:
                self._walk(x, fid, ctx)
        elif isinstance(o, dict):
            c = dict(ctx)
            for k, key in (("data_store", "system"), ("origin_system", "system"), ("system_id", "system"),
                           ("collection", "coll"), ("collection_name", "coll")):
                if isinstance(o.get(k), str):
                    c[key] = o[k]
            if ts(o.get("captured_at")):
                c["t"] = ts(o["captured_at"])
            if isinstance(o.get("resource_id"), str):
                self._record(fid, c.get("t"), c.get("system", ""), c.get("coll", ""), o)
            else:
                for v in o.values():
                    self._walk(v, fid, c)

    # ------------------------------------------------------------------ free text (log / txt / pdf / image-OCR)
    def _lines(self, text, fid, t0):
        m = re.search(r"Snapshot:\s*(\S+)", text)
        header_t = ts(m.group(1)) if m else t0
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        kvs, groups = [], {}
        for l in lines:
            kv = {k: v.strip('"') for k, v in KV_RX.findall(l)}
            kvs.append(kv)
            if kv.get("trace_id"):
                groups.setdefault(kv["trace_id"], []).append(l)
        for l, kv in zip(lines, kvs):
            ids = resources(l)
            if not ids:
                continue
            tm = TS_RX.search(l)
            t = ts(tm.group(0)) if tm else header_t
            low = l.lower()
            system = kv.get("service") or next((s for s in self.systems if s in low), "")
            state = RESULT_MAP.get(kv.get("result", "").lower())
            if not state:
                sm = STATE_RX.search(l)
                state = STATE_MAP.get(sm.group(1).upper()) if sm else None
            cm = self.cat_rx.search(l) if self.cat_rx else None
            link = " ".join(groups[kv["trace_id"]]) if kv.get("trace_id") else l
            for r in ids:
                self._add(file_id=fid, t=t, system=system, res=r, coll="", kind="line", state=state, text=l,
                          link_text=link, hint=cm.group(1) if cm else "", table="")

    # ------------------------------------------------------------------ search
    def scan(self, matcher, audit_at):
        out = []
        for o in self.obs:
            if audit_at and o["t"] and o["t"] > audit_at:
                continue
            if matcher.find(o["link_text"]) or matcher.has_uid(o["link_text"]):
                out.append(o)
        return out
