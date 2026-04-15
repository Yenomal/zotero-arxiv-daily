from datetime import datetime
from html import escape
from pathlib import Path
import re

from loguru import logger
from omegaconf import DictConfig
from pyzotero import zotero

from .base import BaseSink
from ..protocol import Paper
from ..utils import build_collection_path_maps, normalize_arxiv_id, note_to_html


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


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")


class ZoteroSink(BaseSink):
    def __init__(self, config: DictConfig):
        super().__init__(config)
        self.zot = zotero.Zotero(config.zotero.user_id, "user", config.zotero.api_key)
        self.collection_key = self._resolve_collection_key(config.output.zotero.collection_path)
        self.existing_urls, self.existing_dois, self.existing_source_ids = self._load_existing_identifiers()

    def _resolve_collection_key(self, collection_path: str) -> str:
        collections = self.zot.everything(self.zot.collections())
        _, path_to_key = build_collection_path_maps(collections)
        if collection_path not in path_to_key:
            raise ValueError(f"Output Zotero collection path not found: {collection_path}")
        return path_to_key[collection_path]

    def _load_existing_identifiers(self) -> tuple[set[str], set[str], set[str]]:
        existing_urls: set[str] = set()
        existing_dois: set[str] = set()
        existing_source_ids: set[str] = set()

        items = self.zot.everything(self.zot.collection_items(self.collection_key))
        for item in items:
            data = item.get("data", {})
            url = _normalize_url(data.get("url"))
            if url:
                existing_urls.add(url)

            doi = data.get("DOI")
            if doi:
                existing_dois.add(doi)

            archive_id = normalize_arxiv_id(data.get("archiveID"))
            if archive_id:
                existing_source_ids.add(archive_id)

            extra = data.get("extra", "")
            match = re.search(r"arXiv:\s*([0-9.]+)", extra)
            if match:
                existing_source_ids.add(match.group(1))

        return existing_urls, existing_dois, existing_source_ids

    def _paper_exists(self, paper: Paper) -> bool:
        paper_url = _normalize_url(paper.url)
        if paper_url and paper_url in self.existing_urls:
            return True

        if paper.doi and paper.doi in self.existing_dois:
            return True

        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if source_id and source_id in self.existing_source_ids:
            return True

        return False

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
        template = self.config.output.zotero.note_template
        affiliations = "、".join(paper.affiliations) if paper.affiliations else "未知"
        score = f"{paper.score:.1f}" if paper.score is not None else "未知"
        return template.format(
            score=score,
            tldr=paper.tldr or paper.abstract or "未知",
            affiliations=affiliations,
            local_pdf_path=paper.local_pdf_path or "未保存",
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            url=paper.url,
            title=paper.title,
        )

    def _create_note(self, parent_key: str, paper: Paper) -> None:
        note_text = self._build_note_text(paper)
        note_payload = {
            "itemType": "note",
            "parentItem": parent_key,
            "note": note_to_html(escape(note_text)),
        }
        self.zot.create_items([note_payload])

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
        self.zot.create_items([attachment_payload])

    def _remember(self, paper: Paper) -> None:
        paper_url = _normalize_url(paper.url)
        if paper_url:
            self.existing_urls.add(paper_url)
        if paper.doi:
            self.existing_dois.add(paper.doi)
        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if source_id:
            self.existing_source_ids.add(source_id)

    def deliver(self, papers: list[Paper]) -> None:
        if not papers:
            logger.info("No papers to write to Zotero")
            return

        created = 0
        skipped = 0
        for paper in papers:
            if self._paper_exists(paper):
                skipped += 1
                logger.info(f"Skipping existing Zotero paper: {paper.title}")
                continue

            response = self.zot.create_items([self._paper_to_item(paper)])
            item_key = _extract_created_key(response)
            if item_key is None:
                logger.warning(f"Failed to create Zotero item for {paper.title}: {response}")
                continue

            if self.config.output.zotero.write_note:
                self._create_note(item_key, paper)
            self._create_linked_attachment(item_key, paper)

            self._remember(paper)
            created += 1

        logger.info(f"Zotero write completed: created={created}, skipped={skipped}")
