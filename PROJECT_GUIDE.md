# Project Guide for the Team

## Commands your teammates use

### First time on a laptop

```bat
setup_windows.bat
```

This command:

- checks or installs Python when WinGet is available;
- creates `.venv` automatically;
- installs `requirements.txt`;
- creates `.env` from `.env.example` without overwriting an existing configuration;
- checks or installs Tesseract OCR;
- optionally installs Ollama and downloads `llama3.2:1b`;
- runs a final setup check.

### Start the application

```bat
run_app.bat
```

### Check an installation

```bat
verify_setup.bat
```

### Stop the server

Press `Ctrl + C` in the terminal window.

## Recommended code-study order

1. `app.py` — creates services and selects the workspace.
2. `workspaces/individual.py` — candidate interface and result presentation.
3. `workspaces/hr_screening.py` — multi-file and ZIP screening interface.
4. `services/analysis_service.py` — connects reading, extraction, scoring and reporting.
5. `utils/document_reader.py` — PDF, DOCX, TXT, image and OCR handling.
6. `llm/local_extractor.py` — fast deterministic resume/JD structure extraction.
7. `ats/similarity.py` — dynamic JD-derived requirement matching.
8. `ats/scoring.py` and `ats/ats_engine.py` — score calculation and explanation.
9. `hr/bulk_screening.py` and `utils/zip_resume_reader.py` — bulk processing and ZIP safety.
10. `reports/pdf_report.py` and `reports/charts.py` — report and visualizations.
11. `llm/llm_engine.py` — optional Ollama suggestions and chatbot.
12. `database/db.py` — local SQLite history.

## Suggested division for four members

### Member 1 — Frontend

- `app.py`
- `workspaces/`
- `ui/`
- interactive Plotly charts

### Member 2 — Document processing

- `utils/document_reader.py`
- OCR
- document validation
- `utils/security.py`

### Member 3 — Analysis engine

- `llm/local_extractor.py`
- `ats/similarity.py`
- `ats/scoring.py`
- `ats/ats_engine.py`
- `quality/resume_quality.py`

### Member 4 — HR, reporting and storage

- `hr/bulk_screening.py`
- `utils/zip_resume_reader.py`
- `reports/`
- `database/`
- `analytics/`

## Runtime files not shared in source control

- `.venv/` — installed separately on every laptop
- `.env` — local settings
- `data/*.db` — private saved history
- `uploads/*` — temporary/local uploads
- `reports_output/*` — generated reports
- `__pycache__/` and `.pyc` — Python cache

Do not send a ZIP containing `.venv`; it adds hundreds of megabytes and may not work on another computer.
