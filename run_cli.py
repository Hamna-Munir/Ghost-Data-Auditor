"""CLI: python run_cli.py --data dataset --out output.csv [--groq] [--sample]"""
import argparse, os
from pathlib import Path
from audit.util import read_csv
from audit.pipeline import Auditor
from audit.llm import Groq
from audit.evaluate import evaluate, write_report
from audit.usage import write_usage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset")
    ap.add_argument("--out", default="output.csv")
    ap.add_argument("--groq", action="store_true", help="use Groq for images / ambiguous text (needs GROQ_API_KEY)")
    ap.add_argument("--sample", action="store_true", help="also evaluate on sample_deletion_requests.csv")
    a = ap.parse_args()
    d = Path(a.data)
    llm = Groq() if a.groq else None
    if llm and not llm.enabled:
        raise SystemExit("GROQ_API_KEY not set")
    aud = Auditor(d, llm)
    Path("evaluation").mkdir(exist_ok=True)
    if a.sample and (d / "sample_deletion_requests.csv").exists():
        pred, _ = aud.run_all(read_csv(d / "sample_deletion_requests.csv"))
        m, fails = evaluate(pred, read_csv(d / "sample_output.csv"))
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()})
        from tests.test_synthetic import main as synth
        write_report("evaluation/evaluation_report.md", m, fails, synth())
    req = read_csv(d / "deletion_requests.csv")
    out, _ = aud.run_all(req, progress=lambda p, c: print(f"\r{p:6.1%} {c}", end=""))
    out.to_csv(a.out, index=False)
    write_usage("evaluation/usage_report.md", llm, len(req))
    print(f"\nWrote {a.out}: {len(out)} rows | {out.deletion_status.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
