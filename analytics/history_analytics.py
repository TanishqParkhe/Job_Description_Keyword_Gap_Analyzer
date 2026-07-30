"""Small pandas helpers for the saved-history page."""
from __future__ import annotations

from typing import Any

import pandas as pd


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    columns = ["candidate_name", "job_title", "ats_score", "rating", "created_at"]
    if not records:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(records)
    frame["ats_score"] = pd.to_numeric(frame.get("ats_score"), errors="coerce").fillna(0)
    return frame


def summarize_analyses(records: list[dict[str, Any]]) -> dict[str, Any]:
    frame = records_to_dataframe(records)
    if frame.empty:
        return {"count": 0, "average_score": 0.0, "highest_score": 0.0}
    return {
        "count": int(len(frame)),
        "average_score": round(float(frame["ats_score"].mean()), 2),
        "highest_score": round(float(frame["ats_score"].max()), 2),
    }
