"""Professional Streamlit styling and small presentation helpers."""
from __future__ import annotations

import html
import streamlit as st


CSS = r"""
<style>
:root {
  --brand-1: #4f46e5;
  --brand-2: #7c3aed;
  --brand-3: #0ea5e9;
  --ink: #111827;
  --muted: #64748b;
  --surface: rgba(255,255,255,.92);
  --line: rgba(148,163,184,.24);
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 8% 0%, rgba(79,70,229,.10), transparent 28%),
    radial-gradient(circle at 95% 8%, rgba(14,165,233,.10), transparent 25%),
    #f8fafc;
}
[data-testid="stHeader"] { background: rgba(248,250,252,.76); backdrop-filter: blur(12px); }
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #111827 0%, #172554 52%, #1e1b4b 100%);
  border-right: 1px solid rgba(255,255,255,.08);
}
[data-testid="stSidebar"] * { color: #f8fafc; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #cbd5e1; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  border-radius: 12px;
  padding: .55rem .7rem;
  margin: .2rem 0;
  transition: .18s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.08); }
.block-container { max-width: 1420px; padding-top: 1.4rem; padding-bottom: 4rem; }
.hero-card {
  background: linear-gradient(125deg, #111827 0%, #312e81 52%, #075985 100%);
  border: 1px solid rgba(255,255,255,.14);
  box-shadow: 0 24px 70px rgba(30,41,59,.18);
  border-radius: 24px;
  padding: 2.25rem 2.4rem;
  margin-bottom: 1.35rem;
  position: relative;
  overflow: hidden;
}
.hero-card:after {
  content: "";
  width: 280px; height: 280px; border-radius: 999px;
  background: rgba(255,255,255,.08);
  position: absolute; right: -95px; top: -120px;
}
.hero-kicker { color: #bfdbfe; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; font-size: .78rem; }
.hero-title { color: white; font-size: clamp(2rem,4vw,3.25rem); font-weight: 850; line-height: 1.05; margin: .45rem 0 .7rem; }
.hero-subtitle { color: #dbeafe; font-size: 1.05rem; max-width: 780px; line-height: 1.65; margin: 0; }
.hero-chips { margin-top: 1.25rem; display: flex; gap: .55rem; flex-wrap: wrap; }
.hero-chip { color: #e0f2fe; border: 1px solid rgba(186,230,253,.35); background: rgba(255,255,255,.08); border-radius: 999px; padding: .36rem .75rem; font-size: .82rem; }
.page-title { font-size: 1.7rem; font-weight: 800; color: var(--ink); margin: .15rem 0 .25rem; }
.page-subtitle { color: var(--muted); margin-bottom: 1.1rem; }
.section-label { color: var(--brand-1); font-size: .78rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; margin-bottom: .18rem; }
.section-title { color: var(--ink); font-size: 1.3rem; font-weight: 800; margin-bottom: .25rem; }
.section-copy { color: var(--muted); font-size: .92rem; margin-bottom: .85rem; }
[data-testid="stMetric"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1rem 1.05rem;
  box-shadow: 0 8px 25px rgba(15,23,42,.055);
}
[data-testid="stMetricLabel"] { color: #64748b; font-weight: 650; }
[data-testid="stMetricValue"] { color: #0f172a; font-weight: 800; }
[data-testid="stFileUploader"] {
  background: rgba(255,255,255,.82);
  border: 1px dashed rgba(79,70,229,.35);
  border-radius: 18px;
  padding: .45rem;
}
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {
  border-color: var(--line) !important;
  border-radius: 18px !important;
  box-shadow: 0 10px 30px rgba(15,23,42,.045);
  background: rgba(255,255,255,.78);
}
.stButton > button, .stDownloadButton > button {
  border-radius: 12px;
  font-weight: 750;
  min-height: 2.8rem;
  transition: transform .15s ease, box-shadow .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 25px rgba(79,70,229,.15);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(100deg, var(--brand-1), var(--brand-2));
  border: none;
}
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
[data-testid="stExpander"] { border: 1px solid var(--line); border-radius: 14px; background: rgba(255,255,255,.72); }
[data-testid="stChatMessage"] { border-radius: 15px; border: 1px solid var(--line); background: rgba(255,255,255,.78); }
.status-banner {
  border-radius: 16px; padding: 1rem 1.15rem; margin: .35rem 0 1rem;
  background: linear-gradient(90deg, rgba(79,70,229,.09), rgba(14,165,233,.08));
  border: 1px solid rgba(79,70,229,.18); color: #1e293b;
}
.mini-card {
  border: 1px solid var(--line); background: rgba(255,255,255,.85); border-radius: 16px;
  padding: 1rem 1.05rem; min-height: 112px; box-shadow: 0 8px 25px rgba(15,23,42,.04);
}
.mini-card-title { color: #0f172a; font-weight: 800; margin-bottom: .35rem; }
.mini-card-copy { color: #64748b; font-size: .9rem; line-height: 1.5; }
hr { border-color: rgba(148,163,184,.20) !important; }
@media (max-width: 760px) {
  .hero-card { padding: 1.55rem 1.35rem; border-radius: 18px; }
  .block-container { padding-left: .8rem; padding-right: .8rem; }
}
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero() -> None:
    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">Resume intelligence platform</div>
          <div class="hero-title">Make every application and shortlist more confident.</div>
          <p class="hero-subtitle">Compare a resume with a role, understand the evidence behind every score, or screen an entire candidate batch from one workspace.</p>
          <div class="hero-chips">
            <span class="hero-chip">Explainable job matching</span>
            <span class="hero-chip">Individual resume review</span>
            <span class="hero-chip">HR bulk screening</span>
            <span class="hero-chip">Downloadable reports</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_heading(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="page-title">{html.escape(title)}</div>'
        f'<div class="page-subtitle">{html.escape(subtitle)}</div>',
        unsafe_allow_html=True,
    )


def section_heading(kicker: str, title: str, copy: str = "") -> None:
    safe_copy = f'<div class="section-copy">{html.escape(copy)}</div>' if copy else ""
    st.markdown(
        f'<div class="section-label">{html.escape(kicker)}</div>'
        f'<div class="section-title">{html.escape(title)}</div>{safe_copy}',
        unsafe_allow_html=True,
    )


def status_banner(text: str) -> None:
    st.markdown(
        f'<div class="status-banner">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def mini_card(title: str, copy: str) -> None:
    st.markdown(
        f'<div class="mini-card"><div class="mini-card-title">{html.escape(title)}</div>'
        f'<div class="mini-card-copy">{html.escape(copy)}</div></div>',
        unsafe_allow_html=True,
    )
