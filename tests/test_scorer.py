from omegaconf import open_dict

from tests.canned_responses import make_sample_paper, make_stub_openai_client
from zotero_arxiv_daily.scorer import PaperScorer


def test_scorer_scores_single_paper_and_renders_reading_note(config):
    with open_dict(config):
        config.scorer.enabled = True
        config.executor.max_paper_num = 50
        config.scorer.final_top_k = 10

    scorer = PaperScorer(config, make_stub_openai_client())
    paper = make_sample_paper(score=8.0, full_text="Intro\nMain body\nReferences\nTail")
    paper.original_score = 8.0

    scored = scorer.score_paper(paper)

    assert scored.quality_score == 8.0
    assert scored.novelty_score == 7.0
    assert scored.empirical_score == 9.0
    assert scored.clarity_score == 6.0
    assert scored.final_score == 7.6
    assert "Main body" in scorer._build_user_prompt(paper, scorer._clean_text(paper))
    assert "Tail" not in scorer._build_user_prompt(paper, scorer._clean_text(paper))


def test_scorer_ranks_and_limits_to_final_top_k(config):
    with open_dict(config):
        config.scorer.enabled = True
        config.scorer.final_top_k = 1

    scorer = PaperScorer(config, make_stub_openai_client())

    papers = [
        make_sample_paper(title="Paper A", score=9.0, full_text="Text\nReferences\nTail"),
        make_sample_paper(title="Paper B", score=7.0, full_text="Text\nReferences\nTail"),
    ]
    papers[0].original_score = 9.0
    papers[1].original_score = 7.0

    ranked = scorer.score_and_rank(papers)

    assert len(ranked) == 1
    assert ranked[0].title == "Paper A"
    assert scorer.metrics.paper_count == 2
