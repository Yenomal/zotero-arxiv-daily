from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .utils import ensure_directory


@dataclass
class ScorerMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    paper_count: int = 0


class MetricsWriter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(ensure_directory(output_dir))

    def write(self, metrics: ScorerMetrics) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = (
            f"{timestamp}__input_{metrics.input_tokens}"
            f"__output_{metrics.output_tokens}.txt"
        )
        output_path = self.output_dir / file_name
        output_path.write_text(
            "\n".join(
                [
                    f"input_tokens={metrics.input_tokens}",
                    f"output_tokens={metrics.output_tokens}",
                    f"paper_count={metrics.paper_count}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return output_path
