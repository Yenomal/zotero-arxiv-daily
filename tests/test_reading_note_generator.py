from types import SimpleNamespace

from omegaconf import open_dict

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.reading_note_generator import ReadingNoteGenerator


def test_reading_note_generator_creates_markdown_and_html(config):
    with open_dict(config):
        config.scorer.note.enabled = True

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="# Sample Paper Title\n\n一句话总结\n\n## Background\n\n背景内容"
                            )
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
                )
            )
        )
    )

    generator = ReadingNoteGenerator(config, fake_client)
    paper = make_sample_paper(full_text="Intro\nMain body\nReferences\nTail")
    generated = generator.generate(paper)

    assert generated.reading_note_markdown is not None
    assert generated.reading_note_html is not None
    assert "<h1>Sample Paper Title</h1>" in generated.reading_note_html
    prompt = generator._build_prompt(paper, generator._clean_text(paper))
    assert "Tail" not in prompt
    assert "Sample Paper Title" in prompt
