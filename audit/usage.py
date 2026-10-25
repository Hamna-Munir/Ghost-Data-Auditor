from collections import defaultdict
from .llm import PRICES


def write_usage(path, llm, n_requests):
    calls = llm.calls if llm else []
    per = defaultdict(lambda: [0, 0, 0, 0])
    for c in calls:
        p = per[c["model"]]; p[0] += 1; p[1] += c["inp"]; p[2] += c["out"]; p[3] += c.get("cached", False)
    L = ["# Token Usage & Cost Report", "", f"Final full-dataset run: **{n_requests} requests**.", "",
         "Provider: Groq (OpenAI-compatible API). Deterministic code makes every audit decision; the LLM/VLM is used only "
         "for ambiguous request text and image/scanned evidence, with on-disk caching.", "",
         "| Model | Calls | Cached replays | Input tokens | Output tokens | Est. cost (USD) |", "|---|---|---|---|---|---|"]
    ti = to = tc = tcost = 0
    for m, (n, i, o, ca) in per.items():
        pi, po = PRICES.get(m, (0, 0))
        cost = i / 1e6 * pi + o / 1e6 * po
        L.append(f"| {m} | {n} | {ca} | {i} | {o} | {cost:.4f} |")
        ti += i; to += o; tc += n; tcost += cost
    if not per:
        L.append("| (no LLM calls - fully deterministic run) | 0 | 0 | 0 | 0 | 0.0000 |")
    d = max(n_requests, 1)
    L += ["", "## Overall", "", f"- Model calls: {tc}", f"- Input / output tokens: {ti} / {to}",
          f"- Total tokens: {ti + to}  (avg {(ti + to) / d:.1f} per request)",
          f"- Estimated total cost: ${tcost:.4f}  (avg ${tcost / d:.6f} per request)", "",
          "_Prices are estimates; verify at https://groq.com/pricing. No API keys are stored in this file._"]
    open(path, "w", encoding="utf-8").write("\n".join(L))
