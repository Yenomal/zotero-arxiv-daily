import json
from pathlib import Path
from hydra.utils import to_absolute_path
from loguru import logger
from openai import OpenAI
import tiktoken

from .metrics_writer import ScorerMetrics
from .protocol import Paper
from .text_cleaner import clean_full_text


class PaperScorer:
    def __init__(self, config, openai_client: OpenAI):
        self.config = config
        self.openai_client = openai_client
        self.system_prompt = self._read_text(config.scorer.prompt.system_prompt_path)
        self.user_prompt = self._read_text(config.scorer.prompt.user_prompt_path)
        self.schema = json.loads(self._read_text(config.scorer.prompt.schema_path))
        self.metrics = ScorerMetrics()
        self._encoder = tiktoken.encoding_for_model("gpt-4o")

    def _as_float(self, value) -> float | None:
        if value is None:
            return None
        return float(value)

    def _score_weights(self) -> dict[str, float]:
        defaults = {
            "relevance": 0.6,
            "quality": 0.1,
            "novelty": 0.15,
            "empirical": 0.1,
            "clarity": 0.05,
        }
        configured = self.config.scorer.get("score_weights", {})
        weights = {key: float(configured.get(key, value)) for key, value in defaults.items()}
        if any(weight < 0 for weight in weights.values()):
            raise ValueError("config.scorer.score_weights values must be non-negative")
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("config.scorer.score_weights must contain at least one positive value")
        return {key: value / total for key, value in weights.items()}

    def _calculate_final_score(self, paper: Paper) -> float:
        weights = self._score_weights()
        weighted_scores = [
            (weights["relevance"], paper.original_score),
            (weights["quality"], paper.quality_score),
            (weights["novelty"], paper.novelty_score),
            (weights["empirical"], paper.empirical_score),
            (weights["clarity"], paper.clarity_score),
        ]
        available_scores = [(weight, float(score)) for weight, score in weighted_scores if score is not None]
        total_weight = sum(weight for weight, _ in available_scores)
        return sum(weight * score for weight, score in available_scores) / total_weight

    def _read_text(self, path: str) -> str:
        return Path(to_absolute_path(path)).read_text(encoding="utf-8")

    def _clean_text(self, paper: Paper) -> str:
        headings = list(self.config.scorer.text.cleanup.reference_headings)
        return clean_full_text(paper.full_text, paper.full_text_source, headings) or ""

    def _build_user_prompt(self, paper: Paper, cleaned_text: str) -> str:
        paper_json = json.dumps(
            {
                "title": paper.title,
                "abstract": paper.abstract,
                "original_score": round(self._as_float(paper.original_score) or 0.0, 1),
                "full_text": cleaned_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        return self.user_prompt.format(paper_json=paper_json)

    def _load_json(self, content: str) -> dict:
        original_content = content
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0]
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError as exc:
            preview = original_content[:800].replace("\n", "\\n")
            raise ValueError(f"Failed to parse scorer JSON: {exc}. Response preview: {preview}") from exc

    def _validate_result(self, result: dict) -> None:
        required = self.schema.get("required", [])
        missing = [field for field in required if field not in result]
        if missing:
            raise ValueError(f"Missing scorer fields: {missing}. Available keys: {sorted(result.keys())}")

    def _extract_usage(self, response, user_prompt: str) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        if usage is not None:
            return usage.prompt_tokens or 0, usage.completion_tokens or 0
        return len(self._encoder.encode(user_prompt)), 0

    def score_paper(self, paper: Paper) -> Paper:
        cleaned_text = self._clean_text(paper)
        user_prompt = self._build_user_prompt(paper, cleaned_text)
        estimated_input_tokens = len(self._encoder.encode(user_prompt))
        logger.info(
            "Scorer input prepared for '{}': source={}, full_text_chars={}, cleaned_chars={}, prompt_tokens_est={}",
            paper.title,
            paper.full_text_source or "unknown",
            len(paper.full_text or ""),
            len(cleaned_text),
            estimated_input_tokens,
        )
        response = self.openai_client.chat.completions.create(
            model=self.config.scorer.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=float(self.config.scorer.temperature),
        )
        input_tokens, output_tokens = self._extract_usage(response, user_prompt)
        self.metrics.input_tokens += input_tokens
        self.metrics.output_tokens += output_tokens
        self.metrics.paper_count += 1

        raw_content = response.choices[0].message.content or ""
        logger.debug("Scorer raw response for '{}': {}", paper.title, raw_content[:1200])
        result = self._load_json(raw_content)
        self._validate_result(result)

        paper.quality_score = float(result["quality_score"])
        paper.novelty_score = float(result["novelty_score"])
        paper.empirical_score = float(result["empirical_score"])
        paper.clarity_score = float(result["clarity_score"])
        paper.input_tokens = input_tokens
        paper.output_tokens = output_tokens

        paper.final_score = self._calculate_final_score(paper)
        paper.score = paper.final_score
        logger.info(
            "Scorer output for '{}': input_tokens={}, output_tokens={}, original_score={}, quality={}, novelty={}, empirical={}, clarity={}, final_score={}",
            paper.title,
            input_tokens,
            output_tokens,
            paper.original_score,
            paper.quality_score,
            paper.novelty_score,
            paper.empirical_score,
            paper.clarity_score,
            paper.final_score,
        )
        return paper

    def score_and_rank(self, papers: list[Paper]) -> list[Paper]:
        scored = []
        for paper in papers:
            try:
                scored.append(self.score_paper(paper))
            except Exception as exc:
                logger.exception("Scorer failed for '{}': {}", paper.title, exc)
                fallback_score = self._as_float(paper.original_score)
                paper.final_score = fallback_score
                paper.score = fallback_score
                scored.append(paper)
        scored.sort(key=lambda paper: paper.final_score or float("-inf"), reverse=True)
        return scored[: int(self.config.scorer.final_top_k)]
