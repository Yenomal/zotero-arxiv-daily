"""Shared stub factories for tests. No unittest.mock anywhere."""

from datetime import datetime
from types import SimpleNamespace

from zotero_arxiv_daily.protocol import CorpusPaper, Paper


# ---------------------------------------------------------------------------
# OpenAI client stub
# ---------------------------------------------------------------------------

_AFFILIATION_MARKER = "You are an assistant who perfectly extracts affiliations"
_AFFILIATION_RESPONSE = '["TsingHua University","Peking University"]'
_TLDR_RESPONSE = "Hello! How can I assist you today?"
_SCORER_MARKER = "严格的学术论文评审助手"
_SCORER_RESPONSE = """{
  "quality_score": 8.0,
  "novelty_score": 7.0,
  "empirical_score": 9.0,
  "clarity_score": 6.0
}"""
_READING_NOTE_RESPONSE = """# Sample Paper Title

一句话总结

## Background

背景内容

## Model

模型内容

### Training

训练内容

### Inference

推理内容

## Insight

关键创新

## Others

其他细节

## Thinking

思考内容

## Experiment

1. 消融实验

2. 其他实验
"""


def _make_chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
                index=0,
            )
        ],
        id="chatcmpl-stub",
        created=1765197615,
        model="gpt-4o-mini-2024-07-18",
        object="chat.completion",
    )


def _stub_chat_create(**kwargs):
    messages = kwargs.get("messages", [])
    request_str = str(messages)
    if _AFFILIATION_MARKER in request_str:
        return _make_chat_response(_AFFILIATION_RESPONSE)
    if _SCORER_MARKER in request_str:
        return _make_chat_response(_SCORER_RESPONSE)
    if "阅读笔记" in request_str and "论文标题" in request_str:
        return _make_chat_response(_READING_NOTE_RESPONSE)
    return _make_chat_response(_TLDR_RESPONSE)


def _stub_embeddings_create(**kwargs):
    inputs = kwargs.get("input", [])
    n = len(inputs) if isinstance(inputs, list) else 1
    return SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3], index=i, object="embedding") for i in range(n)],
        model="text-embedding-3-large",
        object="list",
    )


def make_stub_openai_client():
    """Return a SimpleNamespace that quacks like openai.OpenAI().

    chat.completions.create() and embeddings.create() behave identically
    to the Docker mock_openai server that CI previously relied on.
    """
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_stub_chat_create),
        ),
        embeddings=SimpleNamespace(create=_stub_embeddings_create),
    )


# ---------------------------------------------------------------------------
# Zotero client stub
# ---------------------------------------------------------------------------

_DEFAULT_COLLECTIONS = [
    {
        "key": "COL1",
        "data": {"name": "survey", "parentCollection": False},
    },
    {
        "key": "COL2",
        "data": {"name": "topic-a", "parentCollection": "COL1"},
    },
]

_DEFAULT_ITEMS = [
    {
        "data": {
            "title": "Stub Paper 1",
            "abstractNote": "Abstract of stub paper 1.",
            "dateAdded": "2026-01-15T10:00:00Z",
            "collections": ["COL2"],
        },
    },
    {
        "data": {
            "title": "Stub Paper 2",
            "abstractNote": "Abstract of stub paper 2.",
            "dateAdded": "2026-02-20T12:00:00Z",
            "collections": ["COL1"],
        },
    },
]


def make_stub_zotero_client(collections=None, items=None, collection_items_map=None):
    """Return a SimpleNamespace that quacks like pyzotero.zotero.Zotero.

    Supports the call patterns used by Executor.fetch_zotero_corpus():
        zot.everything(zot.collections())
        zot.everything(zot.items(itemType=...))
    """
    cols = collections if collections is not None else _DEFAULT_COLLECTIONS
    itms = items if items is not None else _DEFAULT_ITEMS
    collection_items = collection_items_map if collection_items_map is not None else {}
    created_payloads: list[dict] = []

    def everything(generator):
        return generator

    def collections_fn():
        return cols

    def items_fn(**kwargs):
        return itms

    def collection_items_fn(collection, **kwargs):
        return collection_items.get(collection, [])

    def create_items_fn(payload, parentid=None, last_modified=None):
        result = {"successful": {}}
        for index, item in enumerate(payload):
            key = f"NEW{len(created_payloads) + 1}"
            created_payload = dict(item)
            if parentid is not None:
                created_payload["parentItem"] = parentid
            created_payload["key"] = key
            created_payloads.append(created_payload)
            result["successful"][str(index)] = key
        return result

    stub = SimpleNamespace(
        everything=everything,
        collections=collections_fn,
        items=items_fn,
        collection_items=collection_items_fn,
        create_items=create_items_fn,
    )
    stub.created_payloads = created_payloads
    return stub


# ---------------------------------------------------------------------------
# SMTP stub
# ---------------------------------------------------------------------------


def make_stub_smtp(sent_emails: list):
    """Return a class that records calls to sendmail().

    Usage:
        sent = []
        monkeypatch.setattr(smtplib, "SMTP", make_stub_smtp(sent))
        ...
        assert len(sent) == 1
        sender, recipients, body = sent[0]
    """

    class StubSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, sender, recipients, msg):
            sent_emails.append((sender, recipients, msg))

        def quit(self):
            pass

    return StubSMTP


# ---------------------------------------------------------------------------
# Paper / CorpusPaper factories
# ---------------------------------------------------------------------------


def make_sample_paper(**overrides) -> Paper:
    defaults = dict(
        source="arxiv",
        title="Sample Paper Title",
        authors=["Author A", "Author B", "Author C"],
        abstract="This paper explores a novel approach to widget engineering.",
        url="https://arxiv.org/abs/2026.00001",
        source_id="2026.00001",
        doi="10.48550/arXiv.2026.00001",
        published_at=datetime(2026, 1, 1),
        pdf_url="https://arxiv.org/pdf/2026.00001",
        local_pdf_path=None,
        full_text="\\begin{document} Some text. \\end{document}",
        tldr=None,
        affiliations=None,
        score=None,
    )
    defaults.update(overrides)
    return Paper(**defaults)


def make_sample_corpus(n: int = 3) -> list[CorpusPaper]:
    return [
        CorpusPaper(
            title=f"Corpus Paper {i}",
            abstract=f"Abstract for corpus paper {i}.",
            added_date=datetime(2026, 1, 1 + i),
            paths=[f"2026/survey/topic-{i}"],
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# bioRxiv canned API response
# ---------------------------------------------------------------------------

SAMPLE_BIORXIV_API_RESPONSE = {
    "messages": [{"status": "ok"}],
    "collection": [
        {
            "doi": "10.1101/2026.03.01.000001",
            "title": "A biorxiv paper",
            "authors": "Smith, J.; Doe, A.; Lee, K.",
            "abstract": "We present a novel finding.",
            "date": "2026-03-02",
            "category": "bioinformatics",
            "version": "1",
        },
        {
            "doi": "10.1101/2026.03.01.000002",
            "title": "Another biorxiv paper",
            "authors": "Wang, L.; Chen, M.",
            "abstract": "We replicate a key result.",
            "date": "2026-03-02",
            "category": "genomics",
            "version": "1",
        },
        {
            "doi": "10.1101/2026.03.01.000003",
            "title": "Old biorxiv paper",
            "authors": "Old, R.",
            "abstract": "Yesterday's paper.",
            "date": "2026-03-01",
            "category": "bioinformatics",
            "version": "1",
        },
    ],
}
