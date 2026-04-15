from omegaconf import open_dict

from tests.canned_responses import make_sample_paper, make_stub_zotero_client
from zotero_arxiv_daily.sink.zotero import ZoteroSink


def test_zotero_sink_creates_preprint_and_note(config, monkeypatch):
    collections = [
        {
            "key": "OUT1",
            "data": {"name": "泛读", "parentCollection": False},
        }
    ]
    stub_zot = make_stub_zotero_client(collections=collections, collection_items_map={"OUT1": []})
    monkeypatch.setattr("zotero_arxiv_daily.sink.zotero.zotero.Zotero", lambda *args, **kwargs: stub_zot)

    with open_dict(config):
        config.output.mode = "zotero"
        config.output.zotero.collection_path = "泛读"
        config.output.zotero.write_note = True
        config.output.pdf.dir = "/home/rui/zotero/pdf"

    sink = ZoteroSink(config)
    paper = make_sample_paper(
        source_id="2604.00626",
        doi="10.48550/arXiv.2604.00626",
        local_pdf_path="/home/rui/zotero/pdf/2604.00626.pdf",
        tldr="一行总结",
        affiliations=["TsingHua University"],
        score=8.7,
    )
    sink.deliver([paper])

    assert len(stub_zot.created_payloads) == 3

    item_payload = stub_zot.created_payloads[0]
    assert item_payload["itemType"] == "preprint"
    assert item_payload["collections"] == ["OUT1"]
    assert item_payload["archiveID"] == "2604.00626"
    assert item_payload["DOI"] == "10.48550/arXiv.2604.00626"

    note_payload = stub_zot.created_payloads[1]
    assert note_payload["itemType"] == "note"
    assert note_payload["parentItem"] == "NEW1"
    assert "一行总结" in note_payload["note"]
    assert "/home/rui/zotero/pdf/2604.00626.pdf" in note_payload["note"]

    attachment_payload = stub_zot.created_payloads[2]
    assert attachment_payload["itemType"] == "attachment"
    assert attachment_payload["parentItem"] == "NEW1"
    assert attachment_payload["linkMode"] == "linked_file"
    assert attachment_payload["path"] == "attachments:2604.00626.pdf"
    assert attachment_payload["contentType"] == "application/pdf"


def test_zotero_sink_skips_existing_paper(config, monkeypatch):
    collections = [
        {
            "key": "OUT1",
            "data": {"name": "泛读", "parentCollection": False},
        }
    ]
    existing_items = {
        "OUT1": [
            {
                "data": {
                    "url": "https://arxiv.org/abs/2026.00001",
                    "DOI": "10.48550/arXiv.2026.00001",
                    "archiveID": "2026.00001",
                }
            }
        ]
    }
    stub_zot = make_stub_zotero_client(collections=collections, collection_items_map=existing_items)
    monkeypatch.setattr("zotero_arxiv_daily.sink.zotero.zotero.Zotero", lambda *args, **kwargs: stub_zot)

    with open_dict(config):
        config.output.mode = "zotero"
        config.output.zotero.collection_path = "泛读"
        config.output.zotero.write_note = True

    sink = ZoteroSink(config)
    sink.deliver([make_sample_paper()])

    assert stub_zot.created_payloads == []
