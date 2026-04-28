from datetime import datetime
from html import escape
from pathlib import Path
import re
from time import sleep

import httpx
from hydra.utils import to_absolute_path
from loguru import logger
from omegaconf import DictConfig

from .base import BaseSink
from ..deduper import ExistingPaperIndex
from ..protocol import Paper
from ..utils import normalize_arxiv_id


def _author_to_creator(name: str) -> dict[str, str]:
    return {
        "creatorType": "author",
        "name": name,
    }


def _extract_created_key(response: dict | None) -> str | None:
    if not isinstance(response, dict):
        return None

    for top_level_key in ("successful", "success"):
        successful = response.get(top_level_key)
        if not isinstance(successful, dict) or not successful:
            continue
        first_value = next(iter(successful.values()))
        if isinstance(first_value, str):
            return first_value
        if isinstance(first_value, dict):
            if "key" in first_value:
                return first_value["key"]
            data = first_value.get("data")
            if isinstance(data, dict) and "key" in data:
                return data["key"]
    return None


RETRYABLE_ZOTERO_EXCEPTIONS = (
    httpx.ConnectTimeout,
    httpx.ConnectError,
    httpx.PoolTimeout,
    httpx.ProxyError,
)


class ZoteroSink(BaseSink):
    def __init__(self, config: DictConfig):
        super().__init__(config)
        self.existing_index = ExistingPaperIndex.from_config(config)
        self.zot = self.existing_index.zot
        self.collection_key = self.existing_index.collection_key

    def _create_items_with_retry(self, payload: list[dict], operation: str, paper: Paper):
        max_attempts = int(self.config.output.zotero.get("max_write_attempts", 5))
        retry_delay_sec = float(self.config.output.zotero.get("retry_delay_sec", 5))
        retry_backoff = float(self.config.output.zotero.get("retry_backoff", 2.0))
        if max_attempts < 1:
            max_attempts = 1

        delay = retry_delay_sec
        for attempt in range(1, max_attempts + 1):
            try:
                return self.zot.create_items(payload)
            except RETRYABLE_ZOTERO_EXCEPTIONS as exc:
                if attempt >= max_attempts:
                    raise
                logger.warning(
                    "Zotero {} failed for '{}' on attempt {}/{}: {}. Retrying in {:.1f}s",
                    operation,
                    paper.title,
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
                sleep(delay)
                delay *= retry_backoff

    def _paper_exists(self, paper: Paper) -> bool:
        return self.existing_index.contains(paper)

    def _build_extra(self, paper: Paper) -> str:
        lines = []
        if paper.doi:
            lines.append(f"DOI: {paper.doi}")
        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if source_id:
            lines.append(f"arXiv: {source_id}")
        return "\n".join(lines)

    def _paper_to_item(self, paper: Paper) -> dict:
        item = {
            "itemType": "preprint",
            "title": paper.title,
            "creators": [_author_to_creator(author) for author in paper.authors],
            "abstractNote": paper.abstract,
            "url": paper.url,
            "libraryCatalog": "arXiv.org",
            "collections": [self.collection_key],
        }

        if paper.published_at is not None:
            item["date"] = paper.published_at.strftime("%Y-%m-%d")
        if paper.doi:
            item["DOI"] = paper.doi
        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if source_id:
            item["archive"] = "arXiv"
            item["archiveID"] = source_id

        extra = self._build_extra(paper)
        if extra:
            item["extra"] = extra

        return item

    def _build_note_text(self, paper: Paper) -> str:
        template = self._load_note_template()
        affiliations = "、".join(paper.affiliations) if paper.affiliations else "未知"
        score = f"{paper.score:.1f}" if paper.score is not None else "未知"
        original_score = f"{paper.original_score:.1f}" if paper.original_score is not None else "未知"
        final_score = f"{paper.final_score:.1f}" if paper.final_score is not None else "未知"
        quality_score = f"{paper.quality_score:.1f}" if paper.quality_score is not None else "未知"
        novelty_score = f"{paper.novelty_score:.1f}" if paper.novelty_score is not None else "未知"
        empirical_score = f"{paper.empirical_score:.1f}" if paper.empirical_score is not None else "未知"
        clarity_score = f"{paper.clarity_score:.1f}" if paper.clarity_score is not None else "未知"
        return template.format(
            score=escape(score),
            original_score=escape(original_score),
            final_score=escape(final_score),
            quality_score=escape(quality_score),
            novelty_score=escape(novelty_score),
            empirical_score=escape(empirical_score),
            clarity_score=escape(clarity_score),
            tldr=escape(paper.tldr or paper.abstract or "未知"),
            affiliations=escape(affiliations),
            local_pdf_path=escape(paper.local_pdf_path or "未保存"),
            generated_at=escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            url=escape(paper.url),
            title=escape(paper.title),
        )

    def _load_note_template(self) -> str:
        template_path = self.config.output.zotero.get("note_template_path")
        if template_path:
            resolved_path = Path(to_absolute_path(template_path))
            try:
                return resolved_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                logger.warning(f"Note template file not found, falling back to inline template: {resolved_path}")
        return self.config.output.zotero.note_template

    def _create_note(self, parent_key: str, paper: Paper) -> None:
        note_text = self._build_note_text(paper)
        note_payload = {
            "itemType": "note",
            "parentItem": parent_key,
            "note": note_text,
        }
        self._create_items_with_retry([note_payload], "recommendation note creation", paper)

    def _create_reading_note(self, parent_key: str, paper: Paper) -> None:
        if not paper.reading_note_html:
            return
        note_payload = {
            "itemType": "note",
            "parentItem": parent_key,
            "note": paper.reading_note_html,
        }
        self._create_items_with_retry([note_payload], "reading note creation", paper)

    def _build_attachment_path(self, local_pdf_path: str) -> str:
        pdf_root = Path(self.config.output.pdf.dir).expanduser().resolve()
        pdf_path = Path(local_pdf_path).expanduser().resolve()
        try:
            relative_path = pdf_path.relative_to(pdf_root).as_posix()
            return f"attachments:{relative_path}"
        except ValueError:
            return str(pdf_path)

    def _create_linked_attachment(self, parent_key: str, paper: Paper) -> None:
        if not paper.local_pdf_path:
            return

        attachment_payload = {
            "itemType": "attachment",
            "parentItem": parent_key,
            "linkMode": "linked_file",
            "title": Path(paper.local_pdf_path).name,
            "path": self._build_attachment_path(paper.local_pdf_path),
            "contentType": "application/pdf",
        }
        self._create_items_with_retry([attachment_payload], "linked attachment creation", paper)

    def deliver(self, papers: list[Paper]) -> None:
        if not papers:
            logger.info("No papers to write to Zotero")
            return

        created = 0
        skipped = 0
        failed = 0
        for paper in papers:
            if self._paper_exists(paper):
                skipped += 1
                logger.info(f"Skipping existing Zotero paper: {paper.title}")
                continue

            try:
                response = self._create_items_with_retry(
                    [self._paper_to_item(paper)],
                    "item creation",
                    paper,
                )
            except Exception as exc:
                failed += 1
                logger.error(f"Failed to create Zotero item for {paper.title} after retries: {exc}")
                continue

            item_key = _extract_created_key(response)
            if item_key is None:
                failed += 1
                logger.warning(f"Failed to create Zotero item for {paper.title}: {response}")
                continue

            try:
                if self.config.output.zotero.write_note:
                    self._create_note(item_key, paper)
                    self._create_reading_note(item_key, paper)
                self._create_linked_attachment(item_key, paper)
            except Exception as exc:
                logger.error(f"Failed to create Zotero child item for {paper.title} after retries: {exc}")

            self.existing_index.remember(paper)
            created += 1

        logger.info(f"Zotero write completed: created={created}, skipped={skipped}, failed={failed}")
