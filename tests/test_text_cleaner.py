from zotero_arxiv_daily.text_cleaner import clean_full_text


def test_clean_full_text_truncates_plain_text_at_references():
    text = "\n".join(
        [
            "Introduction",
            "Main content",
            "References",
            "Ref line 1",
            "Ref line 2",
        ]
    )
    cleaned = clean_full_text(text, "html", ["References", "Bibliography"])
    assert "Main content" in cleaned
    assert "Ref line 1" not in cleaned


def test_clean_full_text_truncates_tex_text_at_bibliography():
    text = "\n".join(
        [
            "\\section{Introduction}",
            "Main content",
            "\\bibliography{refs}",
            "tail",
        ]
    )
    cleaned = clean_full_text(text, "tar", ["References", "Bibliography"])
    assert "Main content" in cleaned
    assert "\\bibliography" not in cleaned
    assert "tail" not in cleaned
