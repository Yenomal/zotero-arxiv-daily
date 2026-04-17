from pathlib import Path

from hydra.utils import to_absolute_path
from openai import OpenAI
import tiktoken

from .metrics_writer import ScorerMetrics
from .protocol import Paper
from .text_cleaner import clean_full_text
from .utils import markdown_to_html


class ReadingNoteGenerator:
    def __init__(self, config, openai_client: OpenAI):
        self.config = config
        self.openai_client = openai_client
        self.prompt_template = self._read_text(config.scorer.note.prompt_path)
        self.metrics = ScorerMetrics()
        self._encoder = tiktoken.encoding_for_model("gpt-4o")

    def _read_text(self, path: str) -> str:
        return Path(to_absolute_path(path)).read_text(encoding="utf-8")

    def _clean_text(self, paper: Paper) -> str:
        headings = list(self.config.scorer.text.cleanup.reference_headings)
        return clean_full_text(paper.full_text, paper.full_text_source, headings) or ""

    def _build_prompt(self, paper: Paper, cleaned_text: str) -> str:
        task_prompt = self.prompt_template.format(
            title=paper.title,
            abstract=paper.abstract,
            full_text=cleaned_text,
        )
        return (
            f"{task_prompt}\n\n"
            "论文信息：\n\n"
            f"标题：{paper.title}\n\n"
            f"摘要：{paper.abstract}\n\n"
            f"正文：{cleaned_text}\n"
        )

    def generate(self, paper: Paper) -> Paper:
        cleaned_text = self._clean_text(paper)
        prompt = self._build_prompt(paper, cleaned_text)
        response = self.openai_client.chat.completions.create(
            model=self.config.scorer.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=float(self.config.scorer.temperature),
        )

        usage = getattr(response, "usage", None)
        if usage is not None:
            self.metrics.input_tokens += usage.prompt_tokens or 0
            self.metrics.output_tokens += usage.completion_tokens or 0
        else:
            self.metrics.input_tokens += len(self._encoder.encode(prompt))
        self.metrics.paper_count += 1

        markdown_text = (response.choices[0].message.content or "").strip()
        paper.reading_note_markdown = markdown_text
        paper.reading_note_html = markdown_to_html(markdown_text)
        return paper
