"""Small installation check used by verify_setup.bat."""
from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

REQUIRED_IMPORTS = {
    "streamlit": "Streamlit",
    "fitz": "PyMuPDF",
    "docx": "python-docx",
    "PIL": "Pillow",
    "pytesseract": "pytesseract",
    "pandas": "pandas",
    "sklearn": "scikit-learn",
    "plotly": "Plotly",
    "fpdf": "fpdf2",
}


def main() -> int:
    failures: list[str] = []
    print(f"Python: {sys.version.split()[0]}")
    for module_name, label in REQUIRED_IMPORTS.items():
        try:
            importlib.import_module(module_name)
            print(f"[OK] {label}")
        except Exception as error:
            failures.append(label)
            print(f"[FAIL] {label}: {error}")


    try:
        from ats.ats_engine import ATSEngine
        from llm.llm_engine import LLMEngine

        resume = "SKILLS\nPython, SQL\nPROJECTS\nBuilt a Python SQL dashboard."
        jd = "Role: Data Analyst\nMandatory skills: Python, SQL"
        llm = LLMEngine()
        analysis = ATSEngine().analyze_resume(
            resume_text=resume,
            jd_text=jd,
            resume_data=llm.extract_resume_data(resume),
            jd_data=llm.extract_job_description_data(jd),
            resume_metadata={"extraction_quality_score": 90},
        )
        print(f"[OK] Core analysis engine ({analysis['job_match_score']:.1f}/100 test score)")
    except Exception as error:
        failures.append("Core analysis engine")
        print(f"[FAIL] Core analysis engine: {error}")

    tesseract = shutil.which("tesseract")
    default_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if tesseract or default_tesseract.exists():
        print("[OK] Tesseract OCR")
    else:
        print("[OPTIONAL] Tesseract OCR not found; scanned files will not use OCR.")

    try:
        import ollama
        response = ollama.list()
        models = response.get("models", []) if isinstance(response, dict) else response.models
        names = [getattr(item, "model", "") or (item.get("model", "") if isinstance(item, dict) else "") for item in models]
        if any(name.startswith("llama3.2:1b") for name in names):
            print("[OK] Ollama llama3.2:1b model")
        else:
            print("[OPTIONAL] Ollama model not found; core features still work.")
    except Exception:
        print("[OPTIONAL] Ollama service unavailable; core features still work.")

    if failures:
        print("\nRequired components missing: " + ", ".join(failures))
        return 1
    print("\nCore setup is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
