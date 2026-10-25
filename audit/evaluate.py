import json
import pandas as pd
from .util import natural_key

KEY = lambda s: (s["phase"], s["operation"], s["system_id"], s["resource_id"])
FIELDS = ["phase", "operation", "state", "evidence_id"]


def _steps(x):
    try:
        return json.loads(x) if isinstance(x, str) and x.strip() else []
    except Exception:
        return []


def lcs(a, b):
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            dp[i + 1][j + 1] = dp[i][j] + 1 if a[i] == b[j] else max(dp[i][j + 1], dp[i + 1][j])
    return dp[-1][-1]


def evaluate(pred, gold):
    g = gold.set_index("case_id")
    p = pred.set_index("case_id")
    ids = [c for c in g.index if c in p.index]
    ok_status, tp, fp, fn, seq, field_hit, field_tot, fails = 0, 0, 0, 0, [], {f: 0 for f in FIELDS}, 0, []
    for c in ids:
        gs, ps = _steps(g.loc[c, "steps_json"]), _steps(p.loc[c, "steps_json"])
        s_ok = g.loc[c, "deletion_status"] == p.loc[c, "deletion_status"]
        ok_status += s_ok
        gk, pk = [KEY(s) for s in gs], [KEY(s) for s in ps]
        gset, pset = set(gk), set(pk)
        tp += len(gset & pset); fp += len(pset - gset); fn += len(gset - pset)
        pmap = {KEY(s)[1:]: s for s in ps}
        for s in gs:
            field_tot += 1
            q = pmap.get(KEY(s)[1:])
            for f in FIELDS:
                field_hit[f] += bool(q and q.get(f) == s.get(f))
        sq = 1.0 if not gk and not pk else lcs(gk, pk) / max(len(gk), len(pk))
        seq.append(sq)
        if not s_ok or sq < 1:
            fails.append(dict(case_id=c, gold_status=g.loc[c, "deletion_status"], pred_status=p.loc[c, "deletion_status"],
                              seq_acc=round(sq, 3), missing=sorted(gset - pset)[:4], extra=sorted(pset - gset)[:4]))
    n = max(len(ids), 1)
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return dict(cases=len(ids), status_acc=ok_status / n, step_precision=prec, step_recall=rec,
                step_f1=2 * prec * rec / max(prec + rec, 1e-9), sequence_acc=sum(seq) / n,
                field_acc={f: field_hit[f] / max(field_tot, 1) for f in FIELDS}), pd.DataFrame(fails)


def write_report(path, metrics, fails, custom, notes=""):
    L = ["# Evaluation Report", "", "## Sample-set metrics (agent vs `sample_output.csv`)", "",
         f"- Cases evaluated: **{metrics['cases']}**",
         f"- Case-level status accuracy: **{metrics['status_acc']:.1%}**",
         f"- Step-level precision / recall / F1: **{metrics['step_precision']:.1%} / {metrics['step_recall']:.1%} / {metrics['step_f1']:.1%}**",
         "- Field-level accuracy (over gold steps): " + ", ".join(f"`{k}` {v:.1%}" for k, v in metrics["field_acc"].items()),
         f"- Sequence accuracy (LCS ratio of ordered steps): **{metrics['sequence_acc']:.1%}**", "",
         "## Additional team-created cases (`tests/test_synthetic.py`)", ""]
    L += [f"- {'PASS' if ok else 'FAIL'} - {name}: {detail}" for name, ok, detail in custom]
    L += ["", "## Failures found", ""]
    if fails is None or len(fails) == 0:
        L.append("No mismatches on the evaluated set.")
    else:
        L.append(fails.head(25).to_markdown(index=False))
    L += ["", "## Improvements made", "", notes or "_Fill in after each iteration: what failed, what rule/code changed, metric before -> after._"]
    open(path, "w", encoding="utf-8").write("\n".join(L))
