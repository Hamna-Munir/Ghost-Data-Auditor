"""Run:  python inspect_data.py dataset   -> writes inspect_output.txt (paste its content in chat)."""
import sys, json
from pathlib import Path
import pandas as pd

D = Path(sys.argv[1] if len(sys.argv) > 1 else "dataset")
rd = lambda f: pd.read_csv(D / f, dtype=str, keep_default_na=False)
out = []
P = lambda *a: out.append(" ".join(str(x) for x in a))
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 110); pd.set_option("display.max_rows", 200)

P("## deletion_rules.csv (FULL)"); P(rd("deletion_rules.csv").to_string())
a = rd("system_activity.csv")
P("\n## system_activity: event_type counts"); P(a.event_type.value_counts().to_string())
P("\n## reported_result counts"); P(a.reported_result.value_counts().to_string())
P("\n## one example per event_type"); P(a.groupby("event_type").head(1).to_string())
P("\n## source_system / target_system"); P(a.source_system.value_counts().head(12).to_string()); P(a.target_system.value_counts().head(12).to_string())

m = rd("evidence_files.csv")
m["ext"] = m.file_path.str.extract(r"\.(\w+)$")[0]
P("\n## evidence file types"); P(m.ext.value_counts().to_string())
P("\n## evidence origins"); P(m.origin.value_counts().head(15).to_string())
for ext, g in m.groupby("ext"):
    r = g.iloc[0]
    P(f"\n## SAMPLE [{ext}] {r.file_id} {r.file_path}")
    if ext in ("png", "jpg", "jpeg", "webp", "pdf"):
        P("(binary/image - skipped)"); continue
    try: P((D / r.file_path).read_text(errors="ignore")[:1800])
    except Exception as e: P("cannot read:", e)

req, so = rd("sample_deletion_requests.csv"), rd("sample_output.csv")
P("\n## sample status counts"); P(so.deletion_status.value_counts().to_string())
shown = 0
for st in ("INCOMPLETE", "COMPLETE"):
    for _, r in so[so.deletion_status == st].head(2).iterrows():
        P(f"\n## SAMPLE CASE {r.case_id} {st}")
        P(req[req.case_id == r.case_id].drop(columns=["request_text"]).to_string())
        steps = json.loads(r.steps_json)
        P(json.dumps(steps[:14], indent=0)[:2500])
        for fid in sorted({s["evidence_id"] for s in steps if s["evidence_id"]})[:3]:
            P("   evidence", fid, "->", m[m.file_id == fid].file_path.tolist())
Path("inspect_output.txt").write_text("\n".join(out), encoding="utf-8")
print("Wrote inspect_output.txt", sum(len(x) for x in out), "chars")