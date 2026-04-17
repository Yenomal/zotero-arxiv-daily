from tests.canned_responses import make_sample_paper, make_stub_zotero_client
from zotero_arxiv_daily.deduper import ExistingPaperIndex


def test_existing_paper_index_detects_duplicate_by_url_doi_and_source_id():
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
    index = ExistingPaperIndex(stub_zot, "OUT1")

    duplicate = make_sample_paper()
    non_duplicate = make_sample_paper(
        url="https://arxiv.org/abs/2026.99999",
        source_id="2026.99999",
        doi="10.48550/arXiv.2026.99999",
    )

    assert index.contains(duplicate) is True
    assert index.contains(non_duplicate) is False


def test_existing_paper_index_filters_new_papers():
    stub_zot = make_stub_zotero_client(collection_items_map={"OUT1": []})
    index = ExistingPaperIndex(stub_zot, "OUT1")

    existing = make_sample_paper()
    index.remember(existing)

    new_paper = make_sample_paper(
        title="New Paper",
        url="https://arxiv.org/abs/2026.99999",
        source_id="2026.99999",
        doi="10.48550/arXiv.2026.99999",
    )
    new_papers, skipped = index.filter_new_papers([existing, new_paper])

    assert [paper.title for paper in new_papers] == ["New Paper"]
    assert [paper.title for paper in skipped] == ["Sample Paper Title"]
