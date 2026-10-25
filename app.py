import io, json, os, tempfile, zipfile
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from audit.util import read_csv
from audit.pipeline import Auditor
from audit.llm import Groq
from audit.evaluate import evaluate, write_report
from audit.usage import write_usage
from tests.test_synthetic import main as synthetic_cases

st.set_page_config(page_title="Ghost Data Auditor", page_icon="🛡️", layout="wide")

STATUS_COLOR = {"COMPLETE": "#16a34a", "INCOMPLETE": "#dc2626", "NOT_APPLICABLE": "#64748b"}
STATUS_LABEL = {"COMPLETE": "Complete", "INCOMPLETE": "Incomplete", "NOT_APPLICABLE": "Not applicable"}
ACCENT = "#2563eb"

# ------------------------------------------------------------------ theme
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root{
  --ink:#0f172a; --ink-2:#475569; --muted:#94a3b8; --line:#e2e8f0;
  --paper:#ffffff; --wash:#f1f5f9; --accent:#2563eb; --accent-soft:#dbeafe;
  --nav:#0b1220; --nav-2:#131c2e; --nav-line:#1f2a3f;
}
html, body, [class*="css"], .stApp{font-family:'Inter',system-ui,sans-serif;color:var(--ink)}
.stApp{background:var(--wash)}
#MainMenu, footer{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1.4rem;padding-bottom:3rem;max-width:1280px}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"]{background:var(--nav);border-right:1px solid var(--nav-line)}
section[data-testid="stSidebar"] *{color:#cbd5e1}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3{color:#f8fafc!important;font-weight:600;font-size:.95rem}
section[data-testid="stSidebar"] hr{border-color:var(--nav-line)}
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"]>div{background:var(--nav-2)!important;border:1px solid var(--nav-line)!important;color:#f1f5f9!important;border-radius:8px}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"]{background:var(--nav-2);border:1px dashed #334155;border-radius:10px}
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button{background:#1e293b;border:1px solid #334155;color:#e2e8f0}
.brand{display:flex;align-items:center;gap:.7rem;padding:.2rem 0 1rem}
.brand-mark{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#2563eb,#38bdf8);
  display:flex;align-items:center;justify-content:center;font-size:1.2rem}
.brand b{display:block;color:#f8fafc;font-size:1rem;line-height:1.1}
.brand small{color:#64748b;font-size:.75rem}
.status-pill{display:flex;align-items:center;gap:.5rem;background:var(--nav-2);border:1px solid var(--nav-line);
  border-radius:10px;padding:.6rem .8rem;font-size:.84rem;margin:.2rem 0 .6rem}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.on{background:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.18)}
.dot.off{background:#64748b}

/* ---------- header ---------- */
.hero{background:linear-gradient(120deg,#0b1220 0%,#14233f 60%,#1d3a73 100%);border-radius:16px;
  padding:1.5rem 1.8rem;margin-bottom:1.1rem;color:#fff;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-60px;top:-60px;width:240px;height:240px;border-radius:50%;
  background:radial-gradient(circle,rgba(56,189,248,.28),transparent 70%)}
.hero h1{margin:0;font-size:1.55rem;font-weight:700;letter-spacing:-.02em;color:#fff}
.hero p{margin:.35rem 0 1rem;color:#cbd5e1;font-size:.92rem;max-width:720px;line-height:1.55}
.flow{display:flex;gap:.5rem;flex-wrap:wrap;position:relative;z-index:1}
.flow .st{display:flex;align-items:center;gap:.5rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);
  padding:.35rem .8rem .35rem .4rem;border-radius:999px;font-size:.8rem;font-weight:500;color:#e2e8f0;transition:all .2s}
.flow .st:hover{background:rgba(255,255,255,.18);transform:translateY(-2px)}
.flow .n{width:20px;height:20px;border-radius:50%;background:#2563eb;color:#fff;font-size:.7rem;font-weight:700;
  display:flex;align-items:center;justify-content:center}

/* ---------- KPI cards (animated) ---------- */
.kpi{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:1rem 1.15rem;position:relative;
  overflow:hidden;transition:transform .22s ease, box-shadow .22s ease, border-color .22s ease;cursor:default;height:100%}
.kpi:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c,#2563eb);transition:width .22s ease}
.kpi:hover{transform:translateY(-4px);box-shadow:0 14px 28px -12px rgba(15,23,42,.25);border-color:var(--c,#2563eb)}
.kpi:hover:before{width:7px}
.kpi .lab{font-size:.8rem;color:var(--ink-2);font-weight:500;display:flex;align-items:center;gap:.45rem}
.kpi .lab i{width:8px;height:8px;border-radius:50%;background:var(--c,#2563eb);display:inline-block}
.kpi .val{font-size:2rem;font-weight:700;letter-spacing:-.03em;margin:.25rem 0 .1rem;color:var(--ink)}
.kpi .sub{font-size:.78rem;color:var(--muted)}
.kpi .bar{height:5px;background:var(--wash);border-radius:99px;margin-top:.6rem;overflow:hidden}
.kpi .bar span{display:block;height:100%;background:var(--c,#2563eb);border-radius:99px;animation:grow .9s ease-out}
@keyframes grow{from{width:0}}

/* ---------- generic panels ---------- */
.panel{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:1rem 1.2rem;margin-bottom:1rem}
.h{font-size:1rem;font-weight:600;margin:1.1rem 0 .6rem;color:var(--ink)}
.field{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:.7rem .9rem;transition:all .2s;height:100%}
.field:hover{border-color:var(--accent);box-shadow:0 8px 18px -10px rgba(37,99,235,.45);transform:translateY(-2px)}
.field small{display:block;color:var(--muted);font-size:.72rem;margin-bottom:.15rem}
.field span{font-size:.88rem;font-weight:500;color:var(--ink);word-break:break-word}

.badge{display:inline-block;padding:.22rem .75rem;border-radius:999px;font-weight:600;font-size:.78rem}
.COMPLETE{background:#dcfce7;color:#166534}.INCOMPLETE{background:#fee2e2;color:#991b1b}.NOT_APPLICABLE{background:#e2e8f0;color:#334155}

.case-head{display:flex;align-items:center;justify-content:space-between;background:var(--paper);border:1px solid var(--line);
  border-radius:14px;padding:.9rem 1.2rem;margin:.6rem 0 1rem}
.case-head code{font-size:1rem;font-weight:600;color:var(--ink);background:transparent}

.step{display:flex;gap:.9rem;background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:.8rem 1rem;
  margin-bottom:.55rem;transition:all .2s}
.step:hover{border-color:var(--accent);transform:translateX(4px);box-shadow:0 8px 18px -12px rgba(37,99,235,.5)}
.step .idx{min-width:30px;height:30px;border-radius:50%;background:var(--accent-soft);color:var(--accent);font-weight:700;
  font-size:.82rem;display:flex;align-items:center;justify-content:center}
.step .body{font-size:.86rem;color:var(--ink-2);line-height:1.5}
.step .body b{color:var(--ink);font-weight:600}
.chip{display:inline-block;background:var(--wash);border:1px solid var(--line);border-radius:6px;padding:.05rem .45rem;
  font-size:.74rem;margin:.15rem .25rem 0 0;color:var(--ink-2)}

/* ---------- streamlit widgets ---------- */
div[data-testid="stMetric"]{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:.9rem 1.1rem;transition:all .2s}
div[data-testid="stMetric"]:hover{transform:translateY(-3px);box-shadow:0 12px 24px -14px rgba(15,23,42,.35)}
.stTabs [data-baseweb="tab-list"]{gap:.3rem;background:var(--paper);padding:.35rem;border-radius:12px;border:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{height:2.4rem;padding:0 1.1rem;border-radius:8px;font-weight:500;color:var(--ink-2)}
.stTabs [aria-selected="true"]{background:var(--accent);color:#fff!important}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"]{display:none}
.stButton>button, .stDownloadButton>button{border-radius:10px;font-weight:600;border:1px solid var(--line);padding:.55rem 1.2rem;transition:all .2s}
.stButton>button:hover, .stDownloadButton>button:hover{transform:translateY(-2px);box-shadow:0 8px 16px -8px rgba(15,23,42,.35)}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff}
.stButton>button[kind="primary"]:hover{background:#1d4ed8}
div[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}
div[role="radiogroup"]{gap:.4rem}
div[role="radiogroup"] label{background:var(--paper);border:1px solid var(--line);border-radius:999px;padding:.25rem .85rem;transition:all .15s}
div[role="radiogroup"] label:hover{border-color:var(--accent)}
details{border-radius:12px!important;border:1px solid var(--line)!important;background:var(--paper)}
button:focus-visible{outline:2px solid var(--accent)!important;outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>

<div class="hero">
  <h1>Ghost Data Auditor</h1>
  <p>Verifies whether every deletion request was fully carried out. Rules make the decision; an LLM is only used to read images and ambiguous text.</p>
  <div class="flow">
    <div class="st"><span class="n">1</span>Identity resolution</div>
    <div class="st"><span class="n">2</span>Evidence scan</div>
    <div class="st"><span class="n">3</span>Policy rules</div>
    <div class="st"><span class="n">4</span>Remediation plan</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ helpers
def kpi(label, value, color=ACCENT, sub="", pct=None):
    bar = f"<div class='bar'><span style='width:{pct:.0f}%'></span></div>" if pct is not None else ""
    return (f"<div class='kpi' style='--c:{color}'><div class='lab'><i></i>{label}</div>"
            f"<div class='val'>{value}</div><div class='sub'>{sub}</div>{bar}</div>")


def style_fig(fig, h=320):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, sans-serif", color="#334155"),
                      legend=dict(orientation="h", y=-0.1))
    return fig


def gauge(title, value):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value * 100, number={"suffix": "%", "valueformat": ".1f"},
        title={"text": title, "font": {"size": 14}},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": ACCENT},
               "steps": [{"range": [0, 60], "color": "#fee2e2"}, {"range": [60, 85], "color": "#fef3c7"},
                         {"range": [85, 100], "color": "#dcfce7"}]}))
    return style_fig(fig, 230)


def step_title(s):
    if not isinstance(s, dict):
        return str(s), []
    for k in ("action", "step", "type", "name", "operation"):
        if k in s:
            rest = [(a, b) for a, b in s.items() if a != k]
            return str(s[k]), rest
    items = list(s.items())
    return (str(items[0][1]), items[1:]) if items else ("Step", [])


ss = st.session_state
ss.setdefault("out", None); ss.setdefault("traces", {}); ss.setdefault("llm", None)

# ------------------------------------------------------------------ sidebar
try:
    key = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", "")
except Exception:
    key = os.getenv("GROQ_API_KEY", "")

with st.sidebar:
    st.markdown("<div class='brand'><div class='brand-mark'>🛡️</div><div><b>Ghost Data Auditor</b><small>Deletion audit agent</small></div></div>",
                unsafe_allow_html=True)
    st.subheader("Dataset")
    up = st.file_uploader("Upload dataset (.zip)", type="zip")
    path = st.text_input("Or folder path", value="dataset")
    if up:
        tmp = Path(tempfile.gettempdir()) / "ghost_dataset"
        tmp.mkdir(exist_ok=True)
        zipfile.ZipFile(io.BytesIO(up.getvalue())).extractall(tmp)
        hit = next(tmp.rglob("deletion_requests.csv"), None)
        if hit:
            path = str(hit.parent)
            st.success("Dataset loaded")

    st.divider()
    st.subheader("Language model")
    if key:
        st.markdown("<div class='status-pill'><span class='dot on'></span>Groq connected</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='status-pill'><span class='dot off'></span>Groq not configured</div>", unsafe_allow_html=True)
    use_llm = st.toggle("Use Groq for images and ambiguous text", value=False, disabled=not key)
    model = st.selectbox("Text model", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"], disabled=not key)

D = Path(path)
ok = (D / "deletion_requests.csv").exists()
if not ok:
    st.warning("Dataset not found. Upload the zip or enter the folder path in the sidebar.")


def make_auditor():
    llm = Groq(api_key=key, model=model) if (use_llm and key) else None
    ss.llm = llm
    return Auditor(D, llm)


t1, t2, t3, t4, t5 = st.tabs(["Run audit", "Case explorer", "Evaluation", "Usage", "Submission"])

# ------------------------------------------------------------------ run
with t1:
    if ok:
        req = read_csv(D / "deletion_requests.csv")
        n_non = int(req.request_text.str.contains("not asking|Do not|don't|only|copy|download",
                                                  case=False, regex=True).sum())
        c = st.columns(3)
        c[0].markdown(kpi("Requests loaded", len(req), ACCENT, "From deletion_requests.csv"), unsafe_allow_html=True)
        c[1].markdown(kpi("Likely non-deletion", n_non, "#f59e0b", "Keyword estimate", n_non / max(len(req), 1) * 100),
                      unsafe_allow_html=True)
        c[2].markdown(kpi("Groq", "On" if (use_llm and key) else "Off", "#8b5cf6",
                          "Images and ambiguous text only"), unsafe_allow_html=True)

        st.write("")
        if st.button("Run audit on all requests", type="primary"):
            bar = st.progress(0.0, text="Loading evidence…")
            aud = make_auditor()
            ss.out, ss.traces = aud.run_all(req, progress=lambda p, c_: bar.progress(p, text=f"Auditing {c_}"))
            bar.empty()
            st.success("Audit finished.")

        if ss.out is not None:
            out = ss.out
            vc = out.deletion_status.value_counts()
            total = len(out)
            st.markdown("<div class='h'>Results</div>", unsafe_allow_html=True)
            m = st.columns(4)
            m[0].markdown(kpi("Audited", total, ACCENT, "All cases", 100), unsafe_allow_html=True)
            for i, s in enumerate(["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]):
                n = int(vc.get(s, 0))
                m[i + 1].markdown(kpi(STATUS_LABEL[s], n, STATUS_COLOR[s], f"{n / max(total, 1):.1%} of cases",
                                      n / max(total, 1) * 100), unsafe_allow_html=True)

            st.write("")
            g1, g2 = st.columns(2)
            with g1:
                fig = go.Figure(go.Pie(labels=[STATUS_LABEL[s] for s in vc.index], values=vc.values, hole=.62,
                                       marker=dict(colors=[STATUS_COLOR[s] for s in vc.index],
                                                   line=dict(color="#fff", width=3)),
                                       textinfo="percent", hovertemplate="%{label}: %{value} cases<extra></extra>"))
                fig.update_layout(title="Status distribution",
                                  annotations=[dict(text=f"<b>{total}</b><br>cases", x=.5, y=.5, showarrow=False,
                                                    font=dict(size=16))])
                st.plotly_chart(style_fig(fig), use_container_width=True)
            with g2:
                n_steps = out.steps_json.apply(lambda x: len(json.loads(x)))
                fig = go.Figure()
                for s in ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]:
                    sub = n_steps[out.deletion_status == s]
                    if len(sub):
                        vcs = sub.value_counts().sort_index()
                        fig.add_bar(x=vcs.index.astype(str), y=vcs.values, name=STATUS_LABEL[s],
                                    marker_color=STATUS_COLOR[s],
                                    hovertemplate="%{x} steps: %{y} cases<extra>" + STATUS_LABEL[s] + "</extra>")
                fig.update_layout(title="Remediation steps per case", barmode="stack",
                                  xaxis_title="Steps", yaxis_title="Cases")
                fig.update_yaxes(gridcolor="#e2e8f0")
                st.plotly_chart(style_fig(fig), use_container_width=True)

            st.markdown("<div class='h'>All results</div>", unsafe_allow_html=True)
            pick = st.radio("Filter", ["All"] + [STATUS_LABEL[s] for s in STATUS_COLOR], horizontal=True,
                            label_visibility="collapsed")
            inv = {v: k for k, v in STATUS_LABEL.items()}
            view = out if pick == "All" else out[out.deletion_status == inv[pick]]
            st.dataframe(view, use_container_width=True, height=340)
            if total != len(req):
                st.error(f"Row count mismatch: output has {total} rows, expected {len(req)}.")

# ------------------------------------------------------------------ explorer
with t2:
    if ss.out is None:
        st.info("Run the audit first to browse individual cases.")
    else:
        out = ss.out
        f1, f2 = st.columns([1, 2])
        flt = f1.selectbox("Status", ["All"] + [STATUS_LABEL[s] for s in STATUS_COLOR])
        inv = {v: k for k, v in STATUS_LABEL.items()}
        pool = out if flt == "All" else out[out.deletion_status == inv[flt]]
        if pool.empty:
            st.info("No cases with this status.")
        else:
            cid = f2.selectbox(f"Case ({len(pool)})", pool.case_id)
            row = out[out.case_id == cid].iloc[0]
            st.markdown(
                f"<div class='case-head'><code>{cid}</code>"
                f"<span class='badge {row.deletion_status}'>{STATUS_LABEL[row.deletion_status]}</span></div>",
                unsafe_allow_html=True)

            meta = [c_ for c_ in out.columns if c_ not in ("steps_json", "case_id", "deletion_status")]
            if meta:
                cols = st.columns(min(4, len(meta)))
                for i, c_ in enumerate(meta):
                    cols[i % len(cols)].markdown(
                        f"<div class='field'><small>{c_}</small><span>{row[c_]}</span></div>", unsafe_allow_html=True)
                    if (i + 1) % len(cols) == 0 and i + 1 < len(meta):
                        cols = st.columns(min(4, len(meta)))

            steps = json.loads(row.steps_json)
            a, b = st.columns([3, 2])
            with a:
                st.markdown("<div class='h'>Remediation plan</div>", unsafe_allow_html=True)
                if steps:
                    html = ""
                    for i, s in enumerate(steps, 1):
                        title, rest = step_title(s)
                        chips = "".join(f"<span class='chip'>{k}: {v}</span>" for k, v in rest)
                        html += f"<div class='step'><div class='idx'>{i}</div><div class='body'><b>{title}</b><br>{chips}</div></div>"
                    st.markdown(html, unsafe_allow_html=True)
                else:
                    st.info("No remediation steps for this case.")
            with b:
                st.markdown("<div class='h'>Decision trace</div>", unsafe_allow_html=True)
                st.json(ss.traces.get(cid, {}), expanded=False)

# ------------------------------------------------------------------ evaluation
with t3:
    if ok and (D / "sample_deletion_requests.csv").exists() and (D / "sample_output.csv").exists():
        if st.button("Evaluate on sample set", type="primary"):
            aud = make_auditor()
            pred, _ = aud.run_all(read_csv(D / "sample_deletion_requests.csv"))
            met, fails = evaluate(pred, read_csv(D / "sample_output.csv"))
            ss.eval = (met, fails)
        if ss.get("eval"):
            met, fails = ss.eval
            g = st.columns(3)
            g[0].plotly_chart(gauge("Status accuracy", met["status_acc"]), use_container_width=True)
            g[1].plotly_chart(gauge("Step F1", met["step_f1"]), use_container_width=True)
            g[2].plotly_chart(gauge("Sequence accuracy", met["sequence_acc"]), use_container_width=True)
            st.caption(f"Evaluated on {met['cases']} cases")

            fa = met["field_acc"]
            if isinstance(fa, dict) and fa:
                fig = go.Figure(go.Bar(x=[v * 100 for v in fa.values()], y=list(fa.keys()), orientation="h",
                                       marker_color=ACCENT, hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
                fig.update_layout(title="Field accuracy", xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#e2e8f0"))
                st.plotly_chart(style_fig(fig, 80 + 38 * len(fa)), use_container_width=True)
            else:
                st.write(fa)
            st.markdown("<div class='h'>Failed cases</div>", unsafe_allow_html=True)
            st.dataframe(fails, use_container_width=True)
    else:
        st.info("Add sample_deletion_requests.csv and sample_output.csv to the dataset folder to enable evaluation.")

    st.markdown("<div class='h'>Team-created synthetic cases</div>", unsafe_allow_html=True)
    if st.button("Run synthetic cases"):
        for name, passed, det in synthetic_cases():
            (st.success if passed else st.error)(f"{name}: {det}")

# ------------------------------------------------------------------ usage
with t4:
    llm = ss.llm
    calls = llm.calls if llm else []
    df = pd.DataFrame(calls) if calls else pd.DataFrame()
    cols = st.columns(3)
    cols[0].markdown(kpi("Groq calls", len(calls), "#8b5cf6", "This session"), unsafe_allow_html=True)
    num = [c_ for c_ in df.select_dtypes("number").columns][:2] if not df.empty else []
    for i, c_ in enumerate(num):
        cols[i + 1].markdown(kpi(c_.replace("_", " ").title(), f"{df[c_].sum():,.0f}", ACCENT, "Total"),
                             unsafe_allow_html=True)
    st.write("")
    if calls:
        if "model" in df.columns:
            vcm = df.model.value_counts()
            fig = go.Figure(go.Bar(x=vcm.index, y=vcm.values, marker_color="#8b5cf6"))
            fig.update_layout(title="Calls by model")
            st.plotly_chart(style_fig(fig, 260), use_container_width=True)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No LLM calls were made. This run was fully deterministic.")

# ------------------------------------------------------------------ submission
with t5:
    items = [("output.csv", "Exactly 518 rows"),
             ("code.zip", "This project, without dataset/, data/ and .venv"),
             ("log.txt", "Chat transcript")]
    cc = st.columns(3)
    for i, (n_, d_) in enumerate(items):
        cc[i].markdown(kpi(n_, f"{i + 1}", "#0ea5e9", d_), unsafe_allow_html=True)
    st.write("")
    if ss.out is not None:
        Path("evaluation").mkdir(exist_ok=True)
        write_usage("evaluation/usage_report.md", ss.llm, len(ss.out))
        d1, d2, _ = st.columns([1, 1, 2])
        d1.download_button("Download output.csv", ss.out.to_csv(index=False), "output.csv", "text/csv", type="primary")
        d2.download_button("Download usage_report.md", Path("evaluation/usage_report.md").read_text(), "usage_report.md")
    else:
        st.info("Run the audit to enable downloads.")