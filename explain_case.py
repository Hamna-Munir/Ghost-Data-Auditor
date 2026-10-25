"""Debug one case:  python explain_case.py dataset case_05   (works for deletion_requests or sample file)"""
import sys, json
from pathlib import Path
import pandas as pd
from audit.util import read_csv
from audit.pipeline import Auditor

d, cid = Path(sys.argv[1]), sys.argv[2]
req = pd.concat([read_csv(d / f) for f in ("deletion_requests.csv", "sample_deletion_requests.csv") if (d / f).exists()])
row = req[req.case_id == cid].iloc[0].to_dict()
a = Auditor(d)
print("unread evidence:", a.store.unread[:10])
status, steps, trace = a.run_case(row)
print("STATUS:", status, "| user_ids:", trace.get("user_ids"), "| identifiers:", trace.get("identifiers"))
print(pd.DataFrame(trace.get("resources", [])).to_string())
print(pd.DataFrame(steps).to_string())
so = d / "sample_output.csv"
if so.exists():
    g = read_csv(so)
    g = g[g.case_id == cid]
    if len(g):
        print("\nEXPECTED:", g.iloc[0].deletion_status)
        print(pd.DataFrame(json.loads(g.iloc[0].steps_json)).to_string())
