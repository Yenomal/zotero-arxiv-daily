from pathlib import Path

from loguru import logger
import requests
from omegaconf import DictConfig

from .protocol import Paper
from .utils import ensure_directory, normalize_arxiv_id


class PdfWriter:
    def __init__(self, config: DictConfig):
        self.config = config
        self.output_dir = Path(ensure_directory(config.output.pdf.dir))

    def _build_file_path(self, paper: Paper) -> Path:
        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if not source_id:
            raise ValueError(f"Cannot determine arXiv id for PDF output: {paper.title}")
        return self.output_dir / f"{source_id}.pdf"

    def _download(self, url: str, file_path: Path) -> None:
        with requests.get(url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            with file_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)

    def write(self, paper: Paper) -> str | None:
        if not paper.pdf_url:
            logger.warning(f"No PDF URL available for {paper.title}")
            return None

        file_path = self._build_file_path(paper)
        if file_path.exists():
            paper.local_pdf_path = str(file_path)
            return paper.local_pdf_path

        self._download(paper.pdf_url, file_path)
        paper.local_pdf_path = str(file_path)
        return paper.local_pdf_path

    def write_all(self, papers: list[Paper]) -> None:
        if not self.config.output.pdf.enabled:
            return

        for paper in papers:
            try:
                self.write(paper)
            except Exception as exc:
                logger.warning(f"Failed to save PDF for {paper.title}: {exc}")
