import re
import pandas as pd
from datetime import datetime, timezone


def read_csv(path):
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def pick(df, *names):
    """Return the first column matching any candidate name (exact first, then substring)."""
    if df is None or len(df.columns) == 0:
        return None
    cols = {c.lower(): c for c in df.columns}
    for n in names:
        if n in cols:
            return cols[n]
    for n in names:
        for lc, c in cols.items():
            if n in lc:
                return c
    return None


def ts(s):
    s = str(s or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]
