import re

from omegaconf import DictConfig, ListConfig
from pyzotero import zotero

from .protocol import Paper
from .utils import build_collection_path_maps, normalize_arxiv_id


def normalize_collection_path(config: DictConfig) -> str:
    collection_path_parts = config.output.zotero.get("collection_path_parts")
    if collection_path_parts is not None:
        if not isinstance(collection_path_parts, (list, ListConfig)):
            raise TypeError(
                "config.output.zotero.collection_path_parts must be a list of path segments."
            )
        if any(not isinstance(part, str) for part in collection_path_parts):
            raise TypeError(
                "config.output.zotero.collection_path_parts must contain only strings."
            )
        return "/".join(collection_path_parts)

    collection_path = config.output.zotero.get("collection_path")
    if not isinstance(collection_path, str) or not collection_path:
        raise ValueError(
            "Either config.output.zotero.collection_path_parts or config.output.zotero.collection_path must be configured."
        )
    return collection_path


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")


class ExistingPaperIndex:
    def __init__(self, zot_client, collection_key: str):
        self.zot = zot_client
        self.collection_key = collection_key
        self.urls: set[str] = set()
        self.dois: set[str] = set()
        self.source_ids: set[str] = set()
        self.reload()

    @classmethod
    def from_config(cls, config: DictConfig):
        zot_client = zotero.Zotero(config.zotero.user_id, "user", config.zotero.api_key)
        collection_path = normalize_collection_path(config)
        collections = zot_client.everything(zot_client.collections())
        _, path_to_key = build_collection_path_maps(collections)
        if collection_path not in path_to_key:
            raise ValueError(f"Output Zotero collection path not found: {collection_path}")
        return cls(zot_client, path_to_key[collection_path])

    def reload(self) -> None:
        self.urls.clear()
        self.dois.clear()
        self.source_ids.clear()

        items = self.zot.everything(self.zot.collection_items(self.collection_key))
        for item in items:
            data = item.get("data", {})
            url = _normalize_url(data.get("url"))
            if url:
                self.urls.add(url)

            doi = data.get("DOI")
            if doi:
                self.dois.add(doi)

            archive_id = normalize_arxiv_id(data.get("archiveID"))
            if archive_id:
                self.source_ids.add(archive_id)

            extra = data.get("extra", "")
            match = re.search(r"arXiv:\s*([0-9.]+)", extra)
            if match:
                self.source_ids.add(match.group(1))

    def contains(self, paper: Paper) -> bool:
        paper_url = _normalize_url(paper.url)
        if paper_url and paper_url in self.urls:
            return True

        if paper.doi and paper.doi in self.dois:
            return True

        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if source_id and source_id in self.source_ids:
            return True

        return False

    def remember(self, paper: Paper) -> None:
        paper_url = _normalize_url(paper.url)
        if paper_url:
            self.urls.add(paper_url)
        if paper.doi:
            self.dois.add(paper.doi)
        source_id = normalize_arxiv_id(paper.source_id or paper.url)
        if source_id:
            self.source_ids.add(source_id)

    def filter_new_papers(self, papers: list[Paper]) -> tuple[list[Paper], list[Paper]]:
        new_papers = []
        skipped_papers = []
        for paper in papers:
            if self.contains(paper):
                skipped_papers.append(paper)
            else:
                new_papers.append(paper)
        return new_papers, skipped_papers
