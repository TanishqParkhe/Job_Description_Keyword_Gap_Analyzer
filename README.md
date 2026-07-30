# Job_Description_Keyword_Gap_Analyzer
A local Streamlit application for two workflows:

Individual Analysis — compare one resume with one job description, inspect evidence, and download a readable PDF report.
HR Screening — upload many resumes or one ZIP archive, apply a configurable Job Match cutoff, and download shortlisted resumes.
The normal analysis is fast and does not require a cloud API. OCR and the local AI coach are optional enhancements.

First-time setup on Windows
Extract the ZIP to a normal folder, preferably outside OneDrive.
Double-click setup_windows.bat.
Allow it to create .venv and install the Python packages.
Choose whether to install the optional local AI coach.
After setup completes, double-click run_app.bat.
No teammate needs to create or activate a virtual environment manually. The setup script handles it.

Later use
Run only:

run_app.bat
Run setup_windows.bat again only when requirements change or the environment is damaged. It reuses packages already installed in the same .venv.

Main capabilities
PDF, scanned PDF, DOCX, TXT, PNG, JPG and pasted-text resumes
Dynamic requirement discovery from the current job description
No fixed master skill catalogue for matching
Professional experience kept separate from education, projects and internships
Explainable Job Match, Resume Readiness and Confidence scores
Requirement evidence matrix and truth-preserving improvements
PDF report generation
HR bulk screening with direct files or ZIP archives
CSV and shortlisted-resume ZIP downloads
Local SQLite history saved only with user consent
Optional Ollama coach using llama3.2:1b
Important folders
See PROJECT_GUIDE.md for the code-learning order and team-member division.

Privacy
Resumes are processed locally. HR batch files are held in memory for the current session. Individual analyses enter local history only when the user selects the save option.
