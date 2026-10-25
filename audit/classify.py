import re

NEG = [r"not asking for (a )?(deletion|erasure)", r"not a request to (erase|delete)", r"don'?t delete",
       r"do not (close|delete)", r"without removing", r"leave (the|my) account", r"keep the account",
       r"not (to )?(delete|close)", r"leave my profile"]
POS = [r"\bdelet", r"\berase", r"\berasure", r"remove my account", r"close (my|this) account",
       r"personal information linked to it", r"eliminaci", r"exclus", r"suppression", r"削除", r"삭제"]


def classify(text, llm=None, case_id=""):
    t = text.lower()
    neg = any(re.search(p, t) for p in NEG)
    pos = any(re.search(p, t) for p in POS)
    if pos and not neg:
        return "DELETE", "explicit deletion request"
    if not pos:
        return "NOT_DELETE", "no deletion intent (update/export/access/other)"
    if llm is not None and llm.enabled:      # ambiguous: both signals present
        out = llm.chat([{"role": "user", "content":
                         'Does this message REQUEST permanent account/personal-data deletion? '
                         'Answer JSON {"delete": true} or {"delete": false}.\n\n' + text}],
                       case_id=case_id, json_mode=True, max_tokens=20)
        if "true" in out.lower():
            return "DELETE", "LLM: deletion requested"
        return "NOT_DELETE", "LLM: no deletion requested"
    return "NOT_DELETE", "negated deletion wording"
