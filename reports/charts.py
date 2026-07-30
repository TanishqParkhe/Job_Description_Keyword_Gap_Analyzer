"""Readable charts for job match, requirement coverage and resume readiness."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import plotly.graph_objects as go

_JOB_KEYS = [
    ("JD requirements", "skill_score"),
    ("Context relevance", "keyword_score"),
    ("Experience requirement", "experience_score"),
    ("Project/portfolio requirement", "project_score"),
    ("Education requirement", "education_score"),
]


def job_score_rows(analysis: dict[str, Any]) -> list[tuple[str, float, bool, float]]:
    breakdown = analysis.get("score_breakdown", {})
    applicability = breakdown.get("applicability", {})
    weights = breakdown.get("job_match_weights", breakdown.get("weights", {}))
    return [
        (
            label,
            float(analysis.get(key, 0) or 0),
            bool(applicability.get(key, True)),
            float(weights.get(key, 0) or 0),
        )
        for label, key in _JOB_KEYS
    ]


def score_rows(analysis: dict[str, Any]) -> list[tuple[str, float, bool]]:
    """Backward-compatible rows used by older callers."""
    return [(label, value, used) for label, value, used, _ in job_score_rows(analysis)]


def score_values(analysis: dict[str, Any]) -> tuple[list[str], list[float]]:
    rows = job_score_rows(analysis)
    return [row[0] for row in rows], [row[1] for row in rows]


def _coverage_counts(analysis: dict[str, Any]) -> dict[str, int]:
    matrix = analysis.get("requirement_matrix", [])
    return {status: sum(1 for row in matrix if row.get("status") == status) for status in ("Strong", "Partial", "Missing")}


def create_plotly_gauge(analysis: dict[str, Any]) -> go.Figure:
    score = float(analysis.get("job_match_score", analysis.get("ats_score", 0)) or 0)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": "/100", "font": {"size": 42}},
            title={"text": "Job Match", "font": {"size": 20}},
            gauge={
                "axis": {"range": [0, 100]},
                "steps": [
                    {"range": [0, 45], "color": "#fee2e2"},
                    {"range": [45, 65], "color": "#fef3c7"},
                    {"range": [65, 80], "color": "#dbeafe"},
                    {"range": [80, 100], "color": "#dcfce7"},
                ],
                "threshold": {"line": {"color": "#111827", "width": 4}, "value": score},
            },
        )
    )
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=55, b=5))
    return fig


def create_plotly_score_chart(analysis: dict[str, Any]) -> go.Figure:
    rows = job_score_rows(analysis)
    labels = [row[0] for row in rows]
    values = [row[1] if row[2] else 0 for row in rows]
    texts = [f"{row[1]:.1f}/100 · {row[3] * 100:.0f}% weight" if row[2] else "Not requested by JD" for row in rows]
    colors = ["#2563eb" if row[2] else "#d1d5db" for row in rows]
    fig = go.Figure(
        go.Bar(
            y=labels,
            x=values,
            orientation="h",
            text=texts,
            textposition="auto",
            marker_color=colors,
            hovertemplate="%{y}<br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(
        title="How the Job Match score was calculated",
        xaxis_title="Section score out of 100",
        xaxis_range=[0, 100],
        height=390,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def create_plotly_requirement_chart(analysis: dict[str, Any]) -> go.Figure:
    counts = _coverage_counts(analysis)
    total = sum(counts.values())
    fig = go.Figure()
    for status, color in (("Strong", "#16a34a"), ("Partial", "#f59e0b"), ("Missing", "#dc2626")):
        value = counts[status]
        fig.add_trace(
            go.Bar(
                y=["JD requirements"],
                x=[value],
                name=status,
                orientation="h",
                marker_color=color,
                text=[f"{status}: {value}" if value else ""],
                textposition="inside",
                hovertemplate=f"{status}: {value}<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack",
        title=f"Requirement coverage · {total} JD requirements detected",
        xaxis_title="Number of requirements",
        height=260,
        margin=dict(l=20, r=20, t=60, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    if total == 0:
        fig.add_annotation(text="No reliable requirements detected", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return fig


def create_plotly_claim_chart(analysis: dict[str, Any]) -> go.Figure:
    claims = analysis.get("claim_strength", {})
    labels = ["Work evidence", "Project evidence", "Listed/summary only"]
    values = [claims.get("professional", 0), claims.get("project", 0), claims.get("listed_only", 0)]
    fig = go.Figure(go.Bar(x=labels, y=values, text=values, textposition="auto", marker_color=["#16a34a", "#2563eb", "#f59e0b"]))
    fig.update_layout(
        title="Strength of evidence behind matched requirements",
        yaxis_title="Requirements",
        height=320,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def create_plotly_readiness_chart(analysis: dict[str, Any]) -> go.Figure:
    labels = ["ATS readability", "Content quality"]
    values = [float(analysis.get("ats_format_score", 0) or 0), float(analysis.get("content_quality_score", 0) or 0)]
    fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", text=[f"{value:.1f}/100" for value in values], textposition="auto", marker_color=["#0ea5e9", "#8b5cf6"]))
    fig.update_layout(title="Resume Readiness (separate from Job Match)", xaxis_range=[0, 100], height=280, margin=dict(l=20, r=20, t=60, b=20))
    return fig


def create_plotly_comparison_chart(results: list[dict[str, Any]]) -> go.Figure:
    roles = [item["role"] for item in results]
    scores = [item["score"] for item in results]
    fig = go.Figure(go.Bar(y=roles, x=scores, orientation="h", text=[f"{score:.1f}" for score in scores], textposition="auto"))
    fig.update_layout(title="Job Match comparison", xaxis_range=[0, 100], height=max(320, 90 + 55 * len(results)))
    return fig


def _save(fig: plt.Figure) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


def create_score_chart_png(analysis: dict[str, Any]) -> bytes:
    rows = job_score_rows(analysis)
    labels = [row[0] for row in rows]
    values = [row[1] if row[2] else 0 for row in rows]
    colors = ["#2563eb" if row[2] else "#d1d5db" for row in rows]
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    bars = ax.barh(labels, values, color=colors)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Section score out of 100")
    ax.set_title("Job Match factors (grey = not requested by the JD)")
    ax.grid(axis="x", alpha=0.2)
    for bar, row in zip(bars, rows):
        label = f"{row[1]:.1f} · {row[3] * 100:.0f}%" if row[2] else "N/A"
        ax.text(min(bar.get_width() + 1.5, 91), bar.get_y() + bar.get_height() / 2, label, va="center", fontsize=9)
    fig.tight_layout()
    return _save(fig)


def create_summary_scores_png(analysis: dict[str, Any]) -> bytes:
    labels = ["Job Match", "Resume Readiness", "Analysis confidence"]
    values = [
        float(analysis.get("job_match_score", analysis.get("ats_score", 0)) or 0),
        float(analysis.get("resume_readiness_score", 0) or 0),
        float(analysis.get("analysis_confidence", 0) or 0),
    ]
    fig, ax = plt.subplots(figsize=(8.2, 2.4))
    bars = ax.barh(labels, values, color=["#2563eb", "#8b5cf6", "#0ea5e9"])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score out of 100")
    ax.grid(axis="x", alpha=0.2)
    for bar, value in zip(bars, values):
        ax.text(min(value + 1.2, 94), bar.get_y() + bar.get_height() / 2, f"{value:.1f}", va="center", fontweight="bold")
    fig.tight_layout()
    return _save(fig)


def create_gauge_png(analysis: dict[str, Any]) -> bytes:
    # Kept for compatibility; the new report uses a clearer three-score bar.
    return create_summary_scores_png(analysis)


def create_coverage_chart_png(analysis: dict[str, Any]) -> bytes:
    counts = _coverage_counts(analysis)
    values = [counts["Strong"], counts["Partial"], counts["Missing"]]
    labels = ["Strong", "Partial", "Missing"]
    colors = ["#16a34a", "#f59e0b", "#dc2626"]
    total = sum(values)
    fig, ax = plt.subplots(figsize=(8.2, 2.05))
    left = 0
    for value, label, color in zip(values, labels, colors):
        ax.barh(["Requirements"], [value], left=left, color=color)
        if value:
            ax.text(
                left + value / 2,
                0,
                f"{label}: {value}",
                ha="center",
                va="center",
                color="white",
                fontweight="bold",
                fontsize=9,
            )
        left += value
    ax.set_xlim(0, max(1, total))
    ax.set_xlabel("Number of requirements found in this JD")
    ax.set_title(f"Requirement coverage ({total} total)", pad=8)
    ax.grid(axis="x", alpha=0.15)
    fig.tight_layout()
    return _save(fig)


def create_claim_chart_png(analysis: dict[str, Any]) -> bytes:
    claims = analysis.get("claim_strength", {})
    labels = ["Work", "Project", "Listed only"]
    values = [claims.get("professional", 0), claims.get("project", 0), claims.get("listed_only", 0)]
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    bars = ax.bar(labels, values, color=["#16a34a", "#2563eb", "#f59e0b"])
    ax.set_ylabel("Requirements")
    ax.set_title("Evidence strength")
    ax.grid(axis="y", alpha=0.2)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.12, str(value), ha="center")
    fig.tight_layout()
    return _save(fig)


def create_readiness_chart_png(analysis: dict[str, Any]) -> bytes:
    labels = ["ATS readability", "Content quality"]
    values = [float(analysis.get("ats_format_score", 0) or 0), float(analysis.get("content_quality_score", 0) or 0)]
    fig, ax = plt.subplots(figsize=(7.5, 2.6))
    bars = ax.barh(labels, values, color=["#0ea5e9", "#8b5cf6"])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score out of 100")
    ax.grid(axis="x", alpha=0.2)
    for bar, value in zip(bars, values):
        ax.text(min(value + 1.2, 94), bar.get_y() + bar.get_height() / 2, f"{value:.1f}", va="center")
    fig.tight_layout()
    return _save(fig)
