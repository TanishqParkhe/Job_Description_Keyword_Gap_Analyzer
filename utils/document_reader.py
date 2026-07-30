"""Universal, defensive reader for PDF, DOCX, TXT and resume images."""

from __future__ import annotations

import io
import math
import re
import zipfile
from pathlib import Path
from typing import BinaryIO, Iterable

import fitz  # PyMuPDF
from PIL import Image, ImageOps

from config import (
    ENABLE_OCR,
    MAX_DOCUMENT_PAGES,
    MAX_DOCX_UNCOMPRESSED_MB,
    MAX_IMAGE_PIXELS,
    MAX_TEXT_CHARACTERS,
    MAX_UPLOAD_SIZE_MB,
    OCR_DPI,
    OCR_LANGUAGE,
    OCR_TIMEOUT_SECONDS,
    TESSERACT_CMD,
)
from models.schemas import DocumentMetadata, DocumentResult
from utils.security import safe_filename
from utils.text_cleaner import clean_text

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None
else:
    configured = Path(TESSERACT_CMD) if TESSERACT_CMD else None
    default_windows = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if configured and configured.exists():
        pytesseract.pytesseract.tesseract_cmd = str(configured)
    elif default_windows.exists():
        pytesseract.pytesseract.tesseract_cmd = str(default_windows)

try:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:  # pragma: no cover
    Document = None
    Paragraph = Table = object


class DocumentReadError(ValueError):
    """Raised when a document cannot be read safely or meaningfully."""


def _read_bytes(source: object) -> tuple[bytes, str]:
    filename = getattr(source, "name", "") or "document"
    if isinstance(source, (str, Path)):
        path = Path(source)
        filename = path.name
        data = path.read_bytes()
    elif isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    elif hasattr(source, "read"):
        if hasattr(source, "seek"):
            source.seek(0)
        data = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
        if isinstance(data, str):
            data = data.encode("utf-8")
    else:
        raise DocumentReadError("Unsupported input object.")

    if not data:
        raise DocumentReadError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise DocumentReadError(f"The file exceeds the {MAX_UPLOAD_SIZE_MB} MB limit.")
    return data, safe_filename(filename)


def detect_file_type(data: bytes, filename: str = "") -> str:
    """Detect the actual type using signatures, not only the extension."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension in {"txt", "text"}:
        return "txt"
    # Plain-text fallback only when the bytes are mostly printable.
    sample = data[:4000]
    printable = sum(byte in b"\t\n\r" or 32 <= byte <= 126 or byte >= 128 for byte in sample)
    if sample and printable / len(sample) > 0.9 and b"\x00" not in sample:
        return "txt"
    raise DocumentReadError("The file type is unsupported or does not match a valid PDF, DOCX, TXT, PNG or JPEG document.")


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1"):
        try:
            value = data.decode(encoding)
            if value.strip():
                return value
        except UnicodeError:
            continue
    raise DocumentReadError("The text file encoding could not be understood.")


def _ocr_image(image: Image.Image) -> str:
    if not ENABLE_OCR:
        raise DocumentReadError("OCR is disabled. Enable OCR to read scanned documents or images.")
    if pytesseract is None:
        raise DocumentReadError("OCR support is not installed. Install pytesseract and Tesseract OCR.")
    prepared = ImageOps.exif_transpose(image).convert("L")
    # Upscale very small images to improve recognition.
    if prepared.width < 1400:
        factor = min(2.5, 1400 / max(prepared.width, 1))
        prepared = prepared.resize((int(prepared.width * factor), int(prepared.height * factor)))
    try:
        return pytesseract.image_to_string(prepared, lang=OCR_LANGUAGE, config="--psm 6", timeout=OCR_TIMEOUT_SECONDS)
    except Exception as error:
        raise DocumentReadError(f"OCR could not process the image: {error}") from error


def _quality_score(text: str, expected_pages: int, pages_read: int, ocr_pages: int, warnings: list[str]) -> float:
    if not text.strip():
        return 0.0
    chars = len(text)
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    alnum_ratio = sum(character.isalnum() or character.isspace() for character in text) / max(chars, 1)
    replacement_ratio = text.count("�") / max(chars, 1)
    score = 35.0
    score += min(30.0, math.log10(max(len(words), 10)) * 12)
    score += alnum_ratio * 25
    score -= replacement_ratio * 300
    if expected_pages:
        score *= min(1.0, pages_read / expected_pages + 0.15)
    if ocr_pages:
        score -= min(12.0, ocr_pages * 2.0)
    score -= min(20.0, len(warnings) * 3.0)
    return round(max(0.0, min(100.0, score)), 2)


def _quality_label(score: float) -> str:
    if score >= 78:
        return "High"
    if score >= 52:
        return "Medium"
    return "Low"


def _detect_columns(blocks: list[tuple], page_width: float, words: list[tuple] | None = None) -> bool:
    usable = [block for block in blocks if len(block) >= 5 and str(block[4]).strip() and block[2] - block[0] > 40]
    # PyMuPDF can merge left/right lines into one wide block. In that case,
    # inspect the first word position of each detected line.
    if words:
        line_starts: dict[tuple[int, int], tuple[float, float]] = {}
        for word in words:
            if len(word) < 8:
                continue
            key = (int(word[5]), int(word[6]))
            current = line_starts.get(key)
            position = (float(word[0]), float(word[1]))
            if current is None or position[0] < current[0]:
                line_starts[key] = position
        left_starts = [item for item in line_starts.values() if item[0] < page_width * 0.35]
        right_starts = [item for item in line_starts.values() if item[0] > page_width * 0.55]
        left_bands = {round(item[1] / 25) for item in left_starts}
        right_bands = {round(item[1] / 25) for item in right_starts}
        if len(left_starts) >= 3 and len(right_starts) >= 3 and len(left_bands & right_bands) >= 2:
            return True
    if len(usable) < 6:
        return False
    left = [block for block in usable if block[0] < page_width * 0.43 and block[2] < page_width * 0.66]
    right = [block for block in usable if block[0] > page_width * 0.42]
    if len(left) < 2 or len(right) < 2:
        return False
    left_y = {round(block[1] / 25) for block in left}
    right_y = {round(block[1] / 25) for block in right}
    return len(left_y & right_y) >= 2


def _ordered_block_text(blocks: list[tuple], page_width: float, multi_column: bool) -> str:
    text_blocks = [block for block in blocks if len(block) >= 5 and str(block[4]).strip()]
    if not multi_column:
        text_blocks.sort(key=lambda block: (round(block[1], 1), round(block[0], 1)))
    else:
        midpoint = page_width * 0.5
        left = [block for block in text_blocks if (block[0] + block[2]) / 2 <= midpoint]
        right = [block for block in text_blocks if (block[0] + block[2]) / 2 > midpoint]
        left.sort(key=lambda block: (round(block[1], 1), round(block[0], 1)))
        right.sort(key=lambda block: (round(block[1], 1), round(block[0], 1)))
        text_blocks = left + right
    return "\n".join(str(block[4]).strip() for block in text_blocks)


def _read_pdf(data: bytes, filename: str) -> DocumentResult:
    warnings: list[str] = []
    layout_flags: list[str] = []
    page_texts: list[str] = []
    ocr_pages: list[int] = []
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as error:
        raise DocumentReadError(f"The PDF is corrupted or unreadable: {error}") from error
    try:
        if document.needs_pass:
            raise DocumentReadError("The PDF is password protected. Remove the password and try again.")
        if document.page_count == 0:
            raise DocumentReadError("The PDF contains no pages.")
        if document.page_count > MAX_DOCUMENT_PAGES:
            raise DocumentReadError(f"The PDF has {document.page_count} pages; the safe limit is {MAX_DOCUMENT_PAGES}.")

        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            blocks = page.get_text("blocks", sort=False)
            is_multi_column = _detect_columns(blocks, page.rect.width, page.get_text("words"))
            if is_multi_column and "Possible multi-column layout" not in layout_flags:
                layout_flags.append("Possible multi-column layout")
            native = clean_text(_ordered_block_text(blocks, page.rect.width, is_multi_column))
            word_count = len(native.split())
            needs_ocr = word_count < 18 or len(native) < 100
            if needs_ocr and ENABLE_OCR:
                try:
                    if page.rect.width > 3000 or page.rect.height > 5000:
                        raise DocumentReadError("The page dimensions are too large for safe OCR rendering.")
                    pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_text = clean_text(_ocr_image(image))
                    if len(ocr_text) > len(native) * 1.15:
                        native = ocr_text
                        ocr_pages.append(page_index + 1)
                except DocumentReadError as error:
                    warnings.append(f"Page {page_index + 1}: {error}")
            if not native:
                warnings.append(f"Page {page_index + 1} produced no readable text.")
            page_texts.append(native)

        text = clean_text("\n\n".join(item for item in page_texts if item))[:MAX_TEXT_CHARACTERS]
        if not text:
            raise DocumentReadError("No readable text could be recovered from this PDF.")
        if ocr_pages:
            warnings.append(f"OCR was used on {len(ocr_pages)} page(s); carefully review extracted names, dates and numbers.")
        score = _quality_score(text, document.page_count, sum(bool(item) for item in page_texts), len(ocr_pages), warnings)
        metadata = DocumentMetadata(
            filename=filename,
            file_type="pdf",
            size_bytes=len(data),
            page_count=document.page_count,
            pages_read=sum(bool(item) for item in page_texts),
            ocr_pages=ocr_pages,
            extraction_quality_score=score,
            extraction_quality=_quality_label(score),
            warnings=warnings,
            layout_flags=layout_flags,
        )
        return DocumentResult(text=text, metadata=metadata, page_texts=page_texts)
    finally:
        document.close()


def _iter_docx_blocks(document) -> Iterable[str]:
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            if paragraph.text.strip():
                yield paragraph.text
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            for row in table.rows:
                values = [clean_text(cell.text) for cell in row.cells]
                line = " | ".join(value for value in values if value)
                if line:
                    yield line


def _read_docx(data: bytes, filename: str) -> DocumentResult:
    if Document is None:
        raise DocumentReadError("DOCX support is not installed. Install python-docx.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            total_uncompressed = sum(item.file_size for item in members)
            if len(members) > 5000 or total_uncompressed > MAX_DOCX_UNCOMPRESSED_MB * 1024 * 1024:
                raise DocumentReadError("The DOCX expands beyond the safe processing limit.")
        document = Document(io.BytesIO(data))
    except DocumentReadError:
        raise
    except Exception as error:
        raise DocumentReadError(f"The DOCX file is corrupted or unreadable: {error}") from error
    lines = list(_iter_docx_blocks(document))
    text = clean_text("\n".join(lines))[:MAX_TEXT_CHARACTERS]
    if not text:
        raise DocumentReadError("The DOCX file contains no readable paragraphs or table text.")
    warnings: list[str] = []
    if any("|" in line for line in lines):
        warnings.append("Table content was flattened into readable rows; verify the order of complex layouts.")
    score = _quality_score(text, 1, 1, 0, warnings)
    return DocumentResult(
        text=text,
        metadata=DocumentMetadata(
            filename=filename, file_type="docx", size_bytes=len(data), page_count=1, pages_read=1,
            extraction_quality_score=score, extraction_quality=_quality_label(score), warnings=warnings,
            layout_flags=["Contains tables"] if warnings else [],
        ),
        page_texts=[text],
    )


def _read_image(data: bytes, filename: str, file_type: str) -> DocumentResult:
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise DocumentReadError(f"The image contains too many pixels for safe processing ({image.width} × {image.height}).")
        image.verify()
        image = Image.open(io.BytesIO(data))
    except Exception as error:
        raise DocumentReadError(f"The image is corrupted or unsupported: {error}") from error
    text = clean_text(_ocr_image(image))[:MAX_TEXT_CHARACTERS]
    if not text:
        raise DocumentReadError("OCR could not recover readable text from the image.")
    warnings = ["The resume was read with OCR. Review names, dates, symbols and numbers before relying on the score."]
    score = _quality_score(text, 1, 1, 1, warnings)
    return DocumentResult(
        text=text,
        metadata=DocumentMetadata(
            filename=filename, file_type=file_type, size_bytes=len(data), page_count=1, pages_read=1,
            ocr_pages=[1], extraction_quality_score=score, extraction_quality=_quality_label(score),
            warnings=warnings, layout_flags=["Image-only source"],
        ),
        page_texts=[text],
    )


def read_document(source: object = None, *, pasted_text: str = "", filename: str = "") -> DocumentResult:
    """Read uploaded or pasted resume content and return text plus diagnostics."""
    if pasted_text and str(pasted_text).strip():
        text = clean_text(pasted_text)[:MAX_TEXT_CHARACTERS]
        if not text:
            raise DocumentReadError("The pasted resume text is empty after cleaning.")
        score = _quality_score(text, 1, 1, 0, [])
        return DocumentResult(
            text=text,
            metadata=DocumentMetadata(
                filename=safe_filename(filename or "pasted_resume.txt"), file_type="text", size_bytes=len(text.encode("utf-8")),
                extraction_quality_score=score, extraction_quality=_quality_label(score),
            ),
            page_texts=[text],
        )
    if source is None:
        raise DocumentReadError("Upload a resume file or paste resume text.")
    data, detected_name = _read_bytes(source)
    filename = safe_filename(filename or detected_name)
    file_type = detect_file_type(data, filename)
    extension = Path(filename).suffix.lower().lstrip(".")
    if file_type == "pdf":
        result = _read_pdf(data, filename)
    elif file_type == "docx":
        result = _read_docx(data, filename)
    elif file_type in {"png", "jpeg"}:
        result = _read_image(data, filename, file_type)
    else:
        text = clean_text(_decode_text(data))[:MAX_TEXT_CHARACTERS]
        if not text:
            raise DocumentReadError("The text file contains no readable content.")
        score = _quality_score(text, 1, 1, 0, [])
        result = DocumentResult(
            text=text,
            metadata=DocumentMetadata(
                filename=filename, file_type="txt", size_bytes=len(data), extraction_quality_score=score,
                extraction_quality=_quality_label(score),
            ),
            page_texts=[text],
        )
    if extension and extension not in {result.metadata.file_type, "jpg" if result.metadata.file_type == "jpeg" else ""}:
        result.metadata.warnings.append(
            f"The filename extension '.{extension}' did not match the detected {result.metadata.file_type.upper()} content."
        )
    return result
