from abc import ABC, abstractmethod

from omegaconf import DictConfig

from ..protocol import Paper


class BaseSink(ABC):
    def __init__(self, config: DictConfig):
        self.config = config

    @abstractmethod
    def deliver(self, papers: list[Paper]) -> None:
        raise NotImplementedError
