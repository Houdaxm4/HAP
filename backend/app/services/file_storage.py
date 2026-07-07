from pathlib import Path

from app.config import get_settings


class FileStorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.upload_dir = Path(self.settings.upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def analysis_dir(self, analysis_id: str) -> Path:
        path = self.upload_dir / analysis_id.lower()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_files(self, analysis_id: str) -> list[Path]:
        directory = self.analysis_dir(analysis_id)
        return sorted(directory.iterdir()) if directory.exists() else []
