# Architecture

```text
app.py
 ├─ workspaces/individual.py
 ├─ workspaces/hr_screening.py
 └─ workspaces/history.py
          │
          ▼
services/analysis_service.py
 ├─ utils/document_reader.py
 ├─ llm/local_extractor.py
 ├─ ats/ats_engine.py
 └─ reports/pdf_report.py
```

## Analysis path

```text
Resume input + Job description
        ↓
Safe document reading / OCR when required
        ↓
Deterministic resume and JD extraction
        ↓
JD-derived requirement matching
        ↓
Job Match + Resume Readiness + Confidence
        ↓
Evidence matrix, actions, charts and PDF report
```

## Optional AI path

The normal analysis does not depend on Ollama. Ollama is contacted only for open-ended coaching or additional suggestions. Common chatbot questions use instant local answers.

## HR path

```text
Multiple files or ZIP
        ↓
ZIP safety checks and supported-file filtering
        ↓
Concurrent local screening
        ↓
Configurable cutoff and optional mandatory gate
        ↓
Selected / rejected / error tables
        ↓
CSV and shortlisted-resume ZIP
```
