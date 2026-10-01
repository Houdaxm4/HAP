"""File upload handling for analysis workbooks."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import UploadFile

from models.analysis import Analysis, AnalysisFiles, UploadedFileMetadata
from models.common import utc_now_iso
from services.safe_io import validate_analysis_id
from settings import max_upload_bytes
from settings import uploads_dir as default_uploads_dir

UPLOADS_DIR = default_uploads_dir()

_WORKBOOK_EXTENSIONS = {".xlsx", ".xlsm"}
_ZIP_MAGIC = b"PK\x03\x04"
_UPLOAD_CHUNK_BYTES = 1024 * 1024

# Form field names accepted by the upload endpoint.
PREFILLED_WORKBOOK_FIELD = "prefilled_workbook"
PREVIOUS_WORKBOOK_FIELD = "previous_workbook"
CUSTOM_RUN_FILTER_FIELD = "custom_run_filter"


class FileUploadError(Exception):
    """Raised when a required upload is missing or invalid."""


class FileService:
    """Save uploaded workbooks under per-analysis directories."""

    def __init__(self, uploads_dir: Path | None = None) -> None:
        self.uploads_dir = uploads_dir or default_uploads_dir()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def analysis_upload_dir(self, analysis_id: str) -> Path:
        """Return (and create) the upload directory for an analysis."""
        directory = self.uploads_dir / validate_analysis_id(analysis_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    async def save_upload(
        self,
        analysis_id: str,
        upload: UploadFile,
        stored_filename: str,
    ) -> UploadedFileMetadata:
        """Write an uploaded file to disk and return its metadata."""
        directory = self.analysis_upload_dir(analysis_id)
        destination = directory / stored_filename

        original_name = upload.filename or stored_filename
        if stored_filename.lower().endswith((".xlsx", ".xlsm")):
            suffix = Path(original_name).suffix.lower()
            if suffix not in _WORKBOOK_EXTENSIONS:
                raise FileUploadError(
                    f"Unsupported file extension '{suffix}' for a workbook. "
                    f"Allowed: {', '.join(sorted(_WORKBOOK_EXTENSIONS))}"
                )

        # Stream to disk in chunks so a huge upload cannot exhaust memory, and stop at the cap.
        limit = max_upload_bytes()
        temp_destination = destination.with_name(destination.name + ".part")
        size = 0
        first_chunk = True
        try:
            with temp_destination.open("wb") as handle:
                while True:
                    chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    if first_chunk:
                        first_chunk = False
                        if stored_filename.lower().endswith((".xlsx", ".xlsm")) and not chunk.startswith(_ZIP_MAGIC):
                            raise FileUploadError("The uploaded workbook is not a valid .xlsx file.")
                    size += len(chunk)
                    if size > limit:
                        raise FileUploadError(
                            f"Upload exceeds the {limit // (1024 * 1024)} MB limit (HAP_MAX_UPLOAD_MB)."
                        )
                    handle.write(chunk)
            if size == 0:
                raise FileUploadError("The uploaded file is empty.")
            temp_destination.replace(destination)
        finally:
            temp_destination.unlink(missing_ok=True)

        return UploadedFileMetadata(
            filename=original_name,
            stored_filename=stored_filename,
            size_bytes=size,
            uploaded_at=utc_now_iso(),
        )

    async def handle_uploads(
        self,
        analysis: Analysis,
        prefilled_workbook: UploadFile | None,
        previous_workbook: UploadFile | None = None,
        custom_run_filter: UploadFile | None = None,
    ) -> Analysis:
        """
        Save provided uploads and merge file metadata into the analysis record.

        ``prefilled_workbook`` is required. Optional files are saved when present.
        """
        if prefilled_workbook is None or not prefilled_workbook.filename:
            raise FileUploadError("prefilled_workbook is required.")

        analysis_id = analysis.analysis_id
        files = AnalysisFiles(
            prefilled_workbook=await self.save_upload(
                analysis_id,
                prefilled_workbook,
                "prefilled_workbook.xlsx",
            )
        )

        if previous_workbook is not None and previous_workbook.filename:
            files.previous_workbook = await self.save_upload(
                analysis_id,
                previous_workbook,
                "previous_workbook.xlsx",
            )

        if custom_run_filter is not None and custom_run_filter.filename:
            stored_name = self._stored_filename(
                custom_run_filter.filename,
                default_stem="custom_run_filter",
                allowed_extensions={".csv", ".xlsx", ".xlsm", ".xls"},
            )
            files.custom_run_filter = await self.save_upload(
                analysis_id,
                custom_run_filter,
                stored_name,
            )

        analysis.files = files
        analysis.status = "uploaded"
        analysis.updated_at = utc_now_iso()
        return analysis

    def get_custom_run_filter_path(self, analysis: Analysis) -> Path:
        """Resolve the on-disk path to the custom_run filter file."""
        if analysis.files.custom_run_filter is None:
            raise FileUploadError("No custom_run_filter has been uploaded for this analysis.")

        path = (
            self.analysis_upload_dir(analysis.analysis_id)
            / analysis.files.custom_run_filter.stored_filename
        )
        if not path.exists():
            raise FileUploadError("custom_run_filter file is missing on disk.")
        return path

    @staticmethod
    def _stored_filename(
        original_filename: str,
        default_stem: str,
        allowed_extensions: set[str],
    ) -> str:
        suffix = Path(original_filename).suffix.lower()
        if suffix not in allowed_extensions:
            raise FileUploadError(
                f"Unsupported file extension '{suffix}' for {default_stem}. "
                f"Allowed: {', '.join(sorted(allowed_extensions))}"
            )
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_filename).stem) or default_stem
        return f"{safe_stem}{suffix}"

    def get_prefilled_workbook_path(self, analysis: Analysis) -> Path:
        """Resolve the on-disk path to the prefilled workbook."""
        if analysis.files.prefilled_workbook is None:
            raise FileUploadError("No prefilled workbook has been uploaded for this analysis.")

        path = (
            self.analysis_upload_dir(analysis.analysis_id)
            / analysis.files.prefilled_workbook.stored_filename
        )
        if not path.exists():
            raise FileUploadError("Prefilled workbook file is missing on disk.")
        return path

    def get_previous_workbook_path(self, analysis: Analysis) -> Path | None:
        """Resolve previous completed workbook path, or None if not uploaded."""
        if analysis.files.previous_workbook is None:
            return None
        path = (
            self.analysis_upload_dir(analysis.analysis_id)
            / analysis.files.previous_workbook.stored_filename
        )
        if not path.exists():
            return None
        return path

