"""SQLite statements used by the local history database."""

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS resume_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_name TEXT NOT NULL,
    job_title TEXT NOT NULL,
    ats_score REAL NOT NULL,
    rating TEXT,
    matched_skills TEXT,
    missing_skills TEXT,
    analysis_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

INSERT_ANALYSIS = """
INSERT INTO resume_analyses
(candidate_name, job_title, ats_score, rating, matched_skills, missing_skills, analysis_json)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

SELECT_RECENT = """
SELECT id, candidate_name, job_title, ats_score, rating,
       matched_skills, missing_skills, analysis_json, created_at
FROM resume_analyses
ORDER BY created_at DESC
LIMIT ?
"""

DELETE_ALL = "DELETE FROM resume_analyses"
