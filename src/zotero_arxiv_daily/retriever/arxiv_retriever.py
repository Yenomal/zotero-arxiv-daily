from .base import BaseRetriever, register_retriever
import arxiv
from arxiv import Result as ArxivResult
from ..protocol import Paper
from ..utils import extract_markdown_from_pdf, extract_tex_code_from_tar, normalize_arxiv_id
from tempfile import TemporaryDirectory
import feedparser
from tqdm import tqdm
import multiprocessing
import os
from queue import Empty
from typing import Any, Callable, TypeVar
from loguru import logger
import requests

T = TypeVar("T")

def _download_file(url: str, path: str, timeout: tuple[float, float]) -> None:
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def _run_in_subprocess(
    result_conn: Any,
    func: Callable[..., T | None],
    args: tuple[Any, ...],
) -> None:
    try:
        result_conn.send(("ok", func(*args)))
    except Exception as exc:
        result_conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        result_conn.close()


def _run_with_hard_timeout(
    func: Callable[..., T | None],
    args: tuple[Any, ...],
    *,
    timeout: float,
    operation: str,
    paper_title: str,
) -> T | None:
    start_methods = multiprocessing.get_all_start_methods()
    context = multiprocessing.get_context("fork" if "fork" in start_methods else start_methods[0])
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(target=_run_in_subprocess, args=(send_conn, func, args))
    process.start()
    send_conn.close()

    try:
        if not recv_conn.poll(timeout):
            raise Empty
        status, payload = recv_conn.recv()
    except Empty:
        if process.is_alive():
            process.kill()
        process.join(5)
        recv_conn.close()
        logger.warning(f"{operation} timed out for {paper_title} after {timeout} seconds")
        return None

    process.join(5)
    recv_conn.close()

    if status == "ok":
        return payload

    logger.warning(f"{operation} failed for {paper_title}: {payload}")
    return None


def _extract_text_from_pdf_worker(pdf_url: str, timeout: tuple[float, float]) -> str:
    with TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "paper.pdf")
        _download_file(pdf_url, path, timeout)
        return extract_markdown_from_pdf(path)


def _extract_text_from_html_worker(html_url: str, timeout: tuple[float, float]) -> str | None:
    import trafilatura

    response = requests.get(html_url, timeout=timeout)
    response.raise_for_status()
    text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
    if not text:
        raise ValueError(f"No text extracted from {html_url}")
    return text


def _extract_text_from_tar_worker(
    source_url: str,
    paper_id: str,
    timeout: tuple[float, float],
    paper_title: str | None = None,
) -> str | None:
    with TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "paper.tar.gz")
        _download_file(source_url, path, timeout)
        file_contents = extract_tex_code_from_tar(path, paper_id, paper_title=paper_title)
        if not file_contents or "all" not in file_contents:
            raise ValueError("Main tex file not found.")
        return file_contents["all"]


@register_retriever("arxiv")
class ArxivRetriever(BaseRetriever):
    def __init__(self, config):
        super().__init__(config)
        if self.config.source.arxiv.category is None:
            raise ValueError("category must be specified for arxiv.")

    def _retrieve_raw_papers(self) -> list[ArxivResult]:
        client = arxiv.Client(num_retries=10, delay_seconds=10)
        query = '+'.join(self.config.source.arxiv.category)
        include_cross_list = self.config.source.arxiv.get("include_cross_list", False)
        # Get the latest paper from arxiv rss feed
        feed = feedparser.parse(f"https://rss.arxiv.org/atom/{query}")
        if 'Feed error for query' in feed.feed.title:
            raise Exception(f"Invalid ARXIV_QUERY: {query}.")
        raw_papers = []
        allowed_announce_types = {"new", "cross"} if include_cross_list else {"new"}
        all_paper_ids = [
            i.id.removeprefix("oai:arXiv.org:")
            for i in feed.entries
            if i.get("arxiv_announce_type", "new") in allowed_announce_types
        ]
        if self.config.executor.debug:
            all_paper_ids = all_paper_ids[:10]

        # Get full information of each paper from arxiv api
        bar = tqdm(total=len(all_paper_ids))
        for i in range(0, len(all_paper_ids), 20):
            search = arxiv.Search(id_list=all_paper_ids[i:i + 20])
            batch = list(client.results(search))
            bar.update(len(batch))
            raw_papers.extend(batch)
        bar.close()

        return raw_papers

    def convert_to_paper(self, raw_paper: ArxivResult) -> Paper:
        title = raw_paper.title
        authors = [a.name for a in raw_paper.authors]
        abstract = raw_paper.summary
        pdf_url = raw_paper.pdf_url
        source_id = normalize_arxiv_id(raw_paper.entry_id)
        doi = getattr(raw_paper, "doi", None) or (f"10.48550/arXiv.{source_id}" if source_id else None)
        published_at = getattr(raw_paper, "published", None)
        return Paper(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            url=raw_paper.entry_id,
            source_id=source_id,
            doi=doi,
            published_at=published_at,
            pdf_url=pdf_url,
            full_text=None,
        )

    def hydrate_paper(self, paper: Paper) -> Paper:
        if not self.retriever_config.full_text.enabled:
            return paper
        if paper.full_text is not None:
            return paper

        full_text = extract_text_from_html(paper, self.retriever_config.full_text)
        if full_text is not None:
            paper.full_text = full_text
            paper.full_text_source = "html"
            return paper

        full_text = extract_text_from_pdf(paper, self.retriever_config.full_text)
        if full_text is not None:
            paper.full_text = full_text
            paper.full_text_source = "pdf"
            return paper

        full_text = extract_text_from_tar(paper, self.retriever_config.full_text)
        if full_text is not None:
            paper.full_text = full_text
            paper.full_text_source = "tar"
        return paper


def _request_timeout(full_text_config) -> tuple[float, float]:
    return (
        float(full_text_config.connect_timeout_sec),
        float(full_text_config.read_timeout_sec),
    )


def extract_text_from_html(paper: Paper, full_text_config) -> str | None:
    html_url = paper.url.replace("http://", "https://").replace("/abs/", "/html/")
    try:
        return _run_with_hard_timeout(
            _extract_text_from_html_worker,
            (html_url, _request_timeout(full_text_config)),
            timeout=float(full_text_config.html_timeout_sec),
            operation="HTML extraction",
            paper_title=paper.title,
        )
    except Exception as exc:
        logger.warning(f"HTML extraction failed for {paper.title}: {exc}")
        return None


def extract_text_from_pdf(paper: Paper, full_text_config) -> str | None:
    if paper.pdf_url is None:
        logger.warning(f"No PDF URL available for {paper.title}")
        return None
    return _run_with_hard_timeout(
        _extract_text_from_pdf_worker,
        (paper.pdf_url, _request_timeout(full_text_config)),
        timeout=float(full_text_config.pdf_timeout_sec),
        operation="PDF extraction",
        paper_title=paper.title,
    )


def extract_text_from_tar(paper: Paper, full_text_config) -> str | None:
    source_id = normalize_arxiv_id(paper.source_id or paper.url)
    if source_id is None:
        logger.warning(f"No source URL available for {paper.title}")
        return None
    source_url = f"https://arxiv.org/e-print/{source_id}"
    return _run_with_hard_timeout(
        _extract_text_from_tar_worker,
        (source_url, paper.url, _request_timeout(full_text_config), paper.title),
        timeout=float(full_text_config.tar_timeout_sec),
        operation="Tar extraction",
        paper_title=paper.title,
    )
