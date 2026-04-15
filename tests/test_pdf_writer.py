from types import SimpleNamespace

from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.pdf_writer import PdfWriter


class _StubResponse:
    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=0):
        yield from self._chunks


def test_pdf_writer_saves_arxiv_pdf(config, monkeypatch, tmp_path):
    with open_dict(config):
        config.output.pdf.enabled = True
        config.output.pdf.dir = str(tmp_path)

    monkeypatch.setattr(
        "zotero_arxiv_daily.pdf_writer.requests.get",
        lambda *args, **kwargs: _StubResponse([b"fake-pdf"]),
    )

    writer = PdfWriter(config)
    paper = make_sample_paper(source_id="2604.00626", pdf_url="https://arxiv.org/pdf/2604.00626")
    output_path = writer.write(paper)

    assert output_path is not None
    assert output_path.endswith("2604.00626.pdf")
    assert paper.local_pdf_path == output_path
    assert (tmp_path / "2604.00626.pdf").read_bytes() == b"fake-pdf"
