"""Central configuration for Bhavya AI Resume Analyzer Team Edition."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
PROJECT_NAME = "Bhavya AI Resume Analyzer"
PROJECT_VERSION = "4.3.1 Team"
UPLOAD_FOLDER = BASE_DIR / "uploads"
REPORT_FOLDER = BASE_DIR / "reports_output"
ASSETS_FOLDER = BASE_DIR / "assets"
DATABASE_FOLDER = BASE_DIR / "data"
SQLITE_PATH = DATABASE_FOLDER / "bhavya_resume.db"
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "png", "jpg", "jpeg"}
SUPPORTED_RESUME_FORMATS = sorted(ALLOWED_EXTENSIONS)
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15"))
MAX_DOCUMENT_PAGES = int(os.getenv("MAX_DOCUMENT_PAGES", "40"))
MAX_DOCX_UNCOMPRESSED_MB = int(os.getenv("MAX_DOCX_UNCOMPRESSED_MB", "50"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "30"))
MAX_TEXT_CHARACTERS = int(os.getenv("MAX_TEXT_CHARACTERS", "250000"))
OCR_DPI = int(os.getenv("OCR_DPI", "220"))
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()
ENABLE_OCR = os.getenv("ENABLE_OCR", "true").lower() in {"1", "true", "yes", "on"}
DEFAULT_ENCODING = "utf-8"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
FAST_OLLAMA_MODEL = os.getenv("FAST_OLLAMA_MODEL", "llama3.2:1b")
DEEP_OLLAMA_MODEL = os.getenv("DEEP_OLLAMA_MODEL", OLLAMA_MODEL)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "220"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
MASK_PII_BEFORE_LLM = os.getenv("MASK_PII_BEFORE_LLM", "true").lower() in {"1", "true", "yes", "on"}

# Job-match weights. Only factors made applicable by the current JD are used,
# then the active weights are renormalised. Resume formatting and writing
# quality are reported separately as Resume Readiness and never inflate fit.
SKILL_WEIGHT = 0.58
KEYWORD_WEIGHT = 0.18
EXPERIENCE_WEIGHT = 0.14
PROJECT_WEIGHT = 0.04
EDUCATION_CERTIFICATION_WEIGHT = 0.06
ATS_FORMAT_WEIGHT = 0.55
CONTENT_QUALITY_WEIGHT = 0.45
REQUIRED_SECTIONS = ["Summary", "Skills", "Projects", "Experience", "Education"]
OPTIONAL_SECTIONS = ["Certifications", "Achievements", "Internships", "Languages", "Volunteer Experience", "Publications"]
CHATBOT_NAME = "Bhavya AI"
REPORT_TITLE = "Resume-Job Match & Resume Readiness Report"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEFAULT_HR_THRESHOLD = int(os.getenv("DEFAULT_HR_THRESHOLD", "60"))
MAX_BULK_RESUMES = int(os.getenv("MAX_BULK_RESUMES", "500"))
BULK_WORKERS = max(1, int(os.getenv("BULK_WORKERS", "4")))
MAX_ZIP_SIZE_MB = int(os.getenv("MAX_ZIP_SIZE_MB", "300"))
MAX_ZIP_UNCOMPRESSED_MB = int(os.getenv("MAX_ZIP_UNCOMPRESSED_MB", "800"))
MAX_ZIP_COMPRESSION_RATIO = float(os.getenv("MAX_ZIP_COMPRESSION_RATIO", "120"))


def ensure_directories() -> None:
    for folder in (UPLOAD_FOLDER, REPORT_FOLDER, ASSETS_FOLDER, DATABASE_FOLDER):
        folder.mkdir(parents=True, exist_ok=True)
