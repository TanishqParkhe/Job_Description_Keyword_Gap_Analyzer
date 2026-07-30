# Cleanup Manifest

The Team Edition was built from the final Version 4.3 flow. The following items were intentionally excluded or removed.

## Runtime and private files

- `.venv/`
- `.env`
- local SQLite history database
- generated reports
- uploaded resumes
- `__pycache__/`, `.pyc` and `.pytest_cache/`

These files are machine-specific, private or automatically regenerated.

## Obsolete development files

- old patch instructions
- old version-by-version change notes
- duplicate manual `test.py`
- older setup and model-removal scripts
- old PDF-reader compatibility wrapper
- unused PySpark module

## Optional complexity removed

- MySQL backend: local history now uses SQLite only
- sentence-transformer model: matching remains dynamic and uses the current resume/JD directly
- PySpark dependency: not used by the application

## Code reorganized for study

- `app.py` now only starts the application and routes workspaces
- individual, HR and history interfaces are in `workspaces/`
- end-to-end analysis orchestration is in `services/analysis_service.py`
- deterministic resume/JD parsing is in `llm/local_extractor.py`
- optional AI coaching remains in `llm/llm_engine.py`
- history analytics moved from the misleading `bigdata/` folder to `analytics/`
- old version-specific tests were replaced with a focused Team Edition smoke suite
