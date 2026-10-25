import re
from .util import pick

# ordered keyword -> data_category (matched against "<collection> <resource prefix>")
KEYWORDS = [("tombstone", "ACCOUNT_TOMBSTONE"), ("delivery", "EMAIL_DELIVERY_LOG"), ("audit", "SECURITY_AUDIT_LOG"),
            ("security", "SECURITY_AUDIT_LOG"), ("legal", "LEGAL_HOLD_RECORD"), ("backup", "BACKUP_ARCHIVE"),
            ("archive", "BACKUP_ARCHIVE"), ("data_flow", "FLOW"), ("flow", "FLOW"),
            ("attachment", "SUPPORT_ATTACHMENT"), ("support", "SUPPORT_MESSAGE"),
            ("telemetry", "PRODUCT_TELEMETRY"), ("analytic", "ANALYTICS_PROFILE"), ("search", "SEARCH_INDEX_ENTRY"),
            ("cache", "CACHE_ENTRY"), ("export", "USER_EXPORT"), ("marketing", "MARKETING_PROFILE"),
            ("secondary", "SECONDARY_IDENTIFIER"), ("alias", "SECONDARY_IDENTIFIER"),
            ("identifier", "SECONDARY_IDENTIFIER"), ("account", "USER_PROFILE"), ("profile", "USER_PROFILE")]


def categorize(res, hint="", coll=""):
    if hint:
        return hint.upper()
    prefix = re.sub(r"_\d+$", "", res or "").lower()
    blob = f"{coll} {prefix}".lower()
    for kw, cat in KEYWORDS:
        if kw in blob:
            return cat
    return "UNKNOWN"


class Rules:
    def __init__(self, df):
        self.cats = {}
        if df is None or df.empty:
            return
        c = pick(df, "data_category", "category")
        a = pick(df, "required_action", "action", "treatment")
        k = pick(df, "condition")
        for r in df.to_dict("records"):
            self.cats[r[c].strip().upper()] = (r[a].strip().upper(), r.get(k, "") if k else "")

    def names(self):
        return list(self.cats)

    def action(self, cat):
        return self.cats.get(cat, ("DELETE", ""))[0]
