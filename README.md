# Ghost Data Auditor — HackerRank Orchestrate (Oct 2026)

Deterministic deletion-audit agent. Code makes every decision; Groq (LLM/VLM) is optional and used only for
images/scanned evidence and ambiguous request text (cached, token-counted).

## Pipeline
`classify` (NOT_APPLICABLE?) → `identity` (closure over identities + audit log, hashes) → `evidence`
(SQL / JSON / log / PDF / image parsed once) → `activity` (state at `audit_at`, active flows, restore paths) →
`rules` (deletion_rules.csv → DELETE/REDACT/ANONYMIZE/RETAIN/BLOCK/DISABLE) → `planner` (ordered steps_json).

## Run
```
pip install -r requirements.txt
streamlit run app.py                                   # UI
python run_cli.py --data dataset --out output.csv --sample   # CLI + evaluation + usage report
python -m tests.test_synthetic                         # team-created cases
```
Optional Groq: `export GROQ_API_KEY=...` and add `--groq` (or toggle in the UI). Never commit keys.

## IMPORTANT – schema assumptions
Column names of the dataset CSVs were inferred (helper `util.pick` matches by name/substring). Run
`--sample`, read `evaluation/evaluation_report.md`, and adjust `audit/rules.py`, `audit/activity.py`,
`audit/evidence.py` where the real headers/semantics differ.
