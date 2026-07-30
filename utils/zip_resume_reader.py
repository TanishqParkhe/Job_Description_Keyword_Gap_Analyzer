"""Safe in-memory extraction of resume files from HR ZIP uploads."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from config import (
    ALLOWED_EXTENSIONS,
    MAX_BULK_RESUMES,
    MAX_UPLOAD_SIZE_MB,
    MAX_ZIP_COMPRESSION_RATIO,
    MAX_ZIP_SIZE_MB,
    MAX_ZIP_UNCOMPRESSED_MB,
)
from utils.security import safe_filename


class ResumeZipError(ValueError):
    """Raised when an uploaded ZIP cannot be processed safely."""


@dataclass(slots=True)
class InMemoryResume:
    """Small UploadedFile-compatible wrapper used by the bulk screener."""

    name: str
    data: bytes

    def getvalue(self) -> bytes:
        return self.data

    def read(self) -> bytes:
        return self.data

    def seek(self, _position: int) -> int:
        return 0


def _uploaded_bytes(source: Any) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    elif hasattr(source, "getvalue"):
        data = bytes(source.getvalue())
    elif hasattr(source, "read"):
        if hasattr(source, "seek"):
            source.seek(0)
        data = bytes(source.read())
        if hasattr(source, "seek"):
            source.seek(0)
    else:
        raise ResumeZipError("The ZIP upload could not be read.")
    if not data:
        raise ResumeZipError("The uploaded ZIP is empty.")
    if len(data) > MAX_ZIP_SIZE_MB * 1024 * 1024:
        raise ResumeZipError(
            f"The ZIP exceeds the {MAX_ZIP_SIZE_MB} MB upload limit."
        )
    return data


def _safe_member_name(member_name: str, used: set[str]) -> str:
    # PurePosixPath handles ZIP member separators consistently on Windows/Linux.
    path = PurePosixPath(member_name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ResumeZipError("The ZIP contains an unsafe file path.")
    name = safe_filename(path.name, default="resume")
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate = name
    counter = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    used.add(candidate.lower())
    return candidate


def extract_resume_zip(source: Any) -> tuple[list[InMemoryResume], list[str]]:
    """Return supported resume files from a ZIP without writing them to disk.

    The function rejects encrypted archives, path traversal, excessive expansion,
    suspicious compression ratios, oversized members and too many resumes.
    Unsupported files are skipped and reported as warnings.
    """
    data = _uploaded_bytes(source)
    warnings: list[str] = []
    resumes: list[InMemoryResume] = []
    used_names: set[str] = set()
    total_uncompressed = 0

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ResumeZipError("The uploaded file is not a valid ZIP archive.") from error

    with archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if not members:
            raise ResumeZipError("The ZIP contains no files.")
        if len(members) > max(MAX_BULK_RESUMES * 4, 2000):
            raise ResumeZipError("The ZIP contains too many entries to process safely.")

        for member in members:
            raw_name = member.filename.replace("\\", "/")
            basename = PurePosixPath(raw_name).name
            if not basename or basename.startswith(".") or raw_name.startswith("__MACOSX/"):
                continue
            if member.flag_bits & 0x1:
                raise ResumeZipError("Password-protected ZIP members are not supported.")

            extension = Path(basename).suffix.lower().lstrip(".")
            if extension not in ALLOWED_EXTENSIONS:
                warnings.append(f"Skipped unsupported file: {basename}")
                continue
            if member.file_size <= 0:
                warnings.append(f"Skipped empty file: {basename}")
                continue
            if member.file_size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                warnings.append(
                    f"Skipped {basename}: larger than {MAX_UPLOAD_SIZE_MB} MB."
                )
                continue

            compressed = max(member.compress_size, 1)
            ratio = member.file_size / compressed
            if ratio > MAX_ZIP_COMPRESSION_RATIO and member.file_size > 2 * 1024 * 1024:
                raise ResumeZipError(
                    "The ZIP has a suspicious compression ratio and was blocked for safety."
                )

            total_uncompressed += member.file_size
            if total_uncompressed > MAX_ZIP_UNCOMPRESSED_MB * 1024 * 1024:
                raise ResumeZipError(
                    f"The ZIP expands beyond the {MAX_ZIP_UNCOMPRESSED_MB} MB safe limit."
                )
            if len(resumes) >= MAX_BULK_RESUMES:
                warnings.append(
                    f"Only the first {MAX_BULK_RESUMES} supported resumes were loaded."
                )
                break

            try:
                payload = archive.read(member)
            except (RuntimeError, OSError, zipfile.BadZipFile) as error:
                warnings.append(f"Could not read {basename}: {error}")
                continue
            name = _safe_member_name(raw_name, used_names)
            resumes.append(InMemoryResume(name=name, data=payload))

    if not resumes:
        raise ResumeZipError(
            "No supported resume files were found. Use PDF, DOCX, TXT, PNG, JPG or JPEG files."
        )
    return resumes, warnings
