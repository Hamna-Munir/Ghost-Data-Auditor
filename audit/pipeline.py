import json
import pandas as pd
from pathlib import Path
from .util import read_csv, ts, natural_key
from .classify import classify
from .identity import resolve, Matcher
from .evidence import EvidenceStore
from .rules import Rules, categorize
from .activity import Activity
from .planner import plan

PRIORITY = ["PRESENT", "ACTIVE", "ENABLED", "REDACTED", "ANONYMIZED", "BLOCKED", "DISABLED", "ABSENT"]
LIVE = {"PRESENT", "ACTIVE", "ENABLED"}
SHARED_WORDS = ("order", "shared", "agent", "retain")


def merge(states):
    return min(states, key=lambda s: PRIORITY.index(s) if s in PRIORITY else 99)


class Auditor:
    def __init__(self, ddir, llm=None):
        d = Path(ddir)
        self.llm = llm
        self.ident, self.audit = read_csv(d / "user_identities.csv"), read_csv(d / "user_audit_log.csv")
        self.act = Activity(read_csv(d / "system_activity.csv"))
        self.rules = Rules(read_csv(d / "deletion_rules.csv"))
        self.store = EvidenceStore(d, read_csv(d / "evidence_files.csv"), llm, self.act.systems, self.rules.names())

    # ------------------------------------------------------------ state of one resource at audit_at
    def resolve_state(self, res, matcher, audit_at):
        obs = [o for o in self.store.by_res.get(res, []) if not (audit_at and o["t"] and o["t"] > audit_at)]
        T = max((o["t"] for o in obs if o["t"]), default=None)
        latest = [o for o in obs if o["t"] == T] if T else obs
        state, cite, exposed, uidref = None, None, set(), False
        if latest:
            state = merge([o["state"] or "PRESENT" for o in latest])
            cite = next(o["file_id"] for o in latest if (o["state"] or "PRESENT") == state)
            for o in latest:
                if (o["state"] or "PRESENT") in LIVE | {"REDACTED", "ANONYMIZED"}:
                    exposed |= matcher.find(o["text"])
                    uidref |= matcher.has_uid(o["text"])
        eff = self.act.effects_after(res, T, audit_at)
        if eff:
            e, state = eff[-1]
            cite, exposed = e["id"], set()
        return state, cite, exposed, uidref, latest

    # ------------------------------------------------------------ one case
    def run_case(self, row):
        cid, audit_at = row["case_id"], ts(row["audit_at"])
        kind, why = classify(row["request_text"], self.llm, cid)
        if kind != "DELETE":
            return "NOT_APPLICABLE", [], {"reason": why}
        ident = resolve(row["email"], self.ident, self.audit)
        m = Matcher(ident)
        R = {o["res"] for o in self.store.scan(m, audit_at)} | self.act.linked(m)
        problems, verified, retained, table = [], [], [], []
        for r in sorted(R):
            state, cite, exposed, uidref, latest = self.resolve_state(r, m, audit_at)
            if state is None:
                continue
            hint = next((o["hint"] for o in latest if o["hint"]), "")
            coll = next((o["coll"] for o in latest if o["coll"]), "")
            cat = categorize(r, hint, coll)
            system = next((o["system"] for o in sorted(latest, key=lambda o: o["kind"] != "record") if o["system"]), "") \
                or next((e["tgt"] for e, _ in self.act.by_res.get(r, [])), "")
            text = " ".join(o["text"] for o in latest).lower()
            action = self.rules.action(cat)
            if cat == "SUPPORT_MESSAGE":
                action = "REDACT" if any(w in text for w in SHARED_WORDS) else "DELETE"
            table.append(dict(resource=r, system=system, category=cat, state=state, action=action,
                              exposed=sorted(exposed), cite=cite))
            self._decide(cat, action, state, exposed, uidref, system, r, cite, problems, verified, retained)
        steps = plan(problems, verified, retained)
        status = "INCOMPLETE" if problems else "COMPLETE"
        return status, steps, dict(user_ids=sorted(ident["user_ids"]), identifiers=len(ident["identifiers"]),
                                   resources=table)

    @staticmethod
    def _decide(cat, action, state, exposed, uidref, s, r, cite, problems, verified, retained):
        if cat == "FLOW":
            if state in LIVE:
                problems.append(("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", s, r, cite))
            elif state == "DISABLED":
                verified.append(("VERIFY_DATA_FLOW_DISABLED", s, r, cite))
            return
        if cat == "BACKUP_ARCHIVE":
            if state in LIVE:
                problems.append(("REPORT_RESTORE_RISK", "BLOCK_RESTORE", s, r, cite))
            elif state == "BLOCKED":
                verified.append(("VERIFY_RESTORE_BLOCKED", s, r, cite))
            return
        if action == "DELETE":
            if state == "ABSENT":
                verified.append(("VERIFY_RECORD_ABSENT", s, r, cite))
            elif state != "BLOCKED" and state != "DISABLED":
                problems.append(("REPORT_REMAINING_RECORD", "DELETE_RECORD", s, r, cite))
        elif action in ("REDACT", "ANONYMIZE"):
            done, op = ("REDACTED", "REDACT_RECORD") if action == "REDACT" else ("ANONYMIZED", "ANONYMIZE_RECORD")
            vop = "VERIFY_RECORD_" + done
            attributable = bool(exposed) or (action == "ANONYMIZE" and uidref)
            if state == done or (state in LIVE and not attributable):
                verified.append((vop, s, r, cite))
            elif state in LIVE | {"REDACTED", "ANONYMIZED"}:
                problems.append(("REPORT_EXPOSED_PII", op, s, r, cite))
        elif action == "RETAIN":
            if state in LIVE:
                if exposed:
                    problems.append(("REPORT_EXPOSED_PII", "REDACT_RECORD", s, r, cite))
                else:
                    retained.append((s, r, cite))


    # ------------------------------------------------------------ all cases
    def run_all(self, requests_df, progress=None):
        out, traces = [], {}
        rows = requests_df.to_dict("records")
        for i, row in enumerate(rows):
            try:
                status, steps, trace = self.run_case(row)
            except Exception as e:
                status, steps, trace = "INCOMPLETE", [], {"error": repr(e)}
            out.append(dict(case_id=row["case_id"], deletion_status=status,
                            steps_json=json.dumps(steps, ensure_ascii=False, separators=(",", ":"))))
            traces[row["case_id"]] = trace
            if progress:
                progress((i + 1) / len(rows), row["case_id"])
        df = pd.DataFrame(out).sort_values("case_id", key=lambda s: s.map(natural_key)).reset_index(drop=True)
        return df, traces
