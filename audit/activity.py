import re
from .util import pick, ts

RES_RX = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)*_\d+\b", re.I)
EXCL_PREFIX = {"user", "activity", "evidence", "case", "rule", "audit", "trace"}
SIMPLE = {"DELETE_RECORD": "ABSENT", "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
          "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "UPDATE_RECORD": "PRESENT",
          "SYNC_RECORD": "PRESENT", "INDEX_RECORD": "PRESENT", "REFRESH_CACHE": "PRESENT",
          "CREATE_EXPORT": "PRESENT", "SEND_EMAIL": "PRESENT"}


def resources(text):
    out = []
    for m in RES_RX.findall(text or ""):
        if m.rsplit("_", 1)[0].lower() not in EXCL_PREFIX and m not in out:
            out.append(m)
    return out


class Activity:
    """Operational log. Only reported_result == SUCCESS is applied (FAILED/PARTIAL are claims we ignore);
    effects only override a snapshot if they happened AFTER it."""

    def __init__(self, df):
        self.ev, self.by_res, self.systems = [], {}, set()
        if df is None or df.empty:
            return
        g = {k: pick(df, *n) for k, n in dict(id=("activity_id",), t=("event_time", "timestamp"), type=("event_type",),
             src=("source_system",), tgt=("target_system",), res=("resource_id",),
             result=("reported_result", "result", "status"), det=("details",)).items()}
        for r in df.to_dict("records"):
            e = {k: (r.get(c, "") if c else "") for k, c in g.items()}
            e["t"], e["type"], e["result"] = ts(e["t"]), e["type"].upper(), e["result"].upper()
            self.systems |= {e["src"], e["tgt"]}
            e["effects"] = self._effects(e)
            self.ev.append(e)
        self.systems.discard("")
        self.ev.sort(key=lambda e: (e["t"] is None, e["t"]))
        for e in self.ev:
            for res, eff in e["effects"]:
                self.by_res.setdefault(res, []).append((e, eff))

    @staticmethod
    def _effects(e):
        if e["result"] != "SUCCESS":
            return []
        t, d, res = e["type"], e["det"].lower(), e["res"]
        if t in SIMPLE:
            return [(res, SIMPLE[t])]
        if t == "CHECK_DATA_FLOW":
            return [(res, "DISABLED" if any(w in d for w in ("disabled", "inactive", "stopped")) else "ENABLED")]
        if t == "CHECK_RESTORE_ACCESS":
            return [(res, "ACTIVE" if ("can still" in d or "restorable" in d) and "cannot" not in d else "BLOCKED")]
        if t == "RESTORE_BACKUP":
            return [(res, "ACTIVE")] + [(x, "PRESENT") for x in resources(e["det"]) if x != res]
        return []

    def linked(self, matcher):
        """Resources that activity text ties to the user (identity-link events, emails/user ids in details)."""
        out = set()
        for e in self.ev:
            if matcher.find(e["det"]) or matcher.has_uid(e["det"]):
                out.add(e["res"])
                out |= set(resources(e["det"]))
        return {r for r in out if r}

    def effects_after(self, res, t0, audit_at):
        return [(e, eff) for e, eff in self.by_res.get(res, [])
                if e["t"] and (audit_at is None or e["t"] <= audit_at) and (t0 is None or e["t"] > t0)]
