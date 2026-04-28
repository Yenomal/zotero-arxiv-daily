from abc import ABC, abstractmethod
from omegaconf import DictConfig
from ..protocol import Paper, CorpusPaper
import numpy as np
from typing import Type
class BaseReranker(ABC):
    def __init__(self, config:DictConfig):
        self.config = config

    def _get_time_decay_weight(self) -> float:
        if self.config is None:
            return 0.0
        weight = float(self.config.reranker.get("time_decay_weight", 0.0))
        if not 0.0 <= weight <= 1.0:
            raise ValueError("config.reranker.time_decay_weight must be between 0.0 and 1.0")
        return weight

    def rerank(self, candidates:list[Paper], corpus:list[CorpusPaper]) -> list[Paper]:
        corpus = sorted(corpus,key=lambda x: x.added_date,reverse=True)
        sim = self.get_similarity_score([c.abstract for c in candidates], [c.abstract for c in corpus])
        assert sim.shape == (len(candidates), len(corpus))
        semantic_scores = sim.mean(axis=1) * 10 # [n_candidate]
        decay_weight = self._get_time_decay_weight()
        if decay_weight > 0:
            recency_weights = 1 / (1 + np.log10(np.arange(len(corpus)) + 1))
            recency_weights: np.ndarray = recency_weights / recency_weights.sum()
            recency_scores = (sim * recency_weights).sum(axis=1) * 10
            scores = (1 - decay_weight) * semantic_scores + decay_weight * recency_scores
        else:
            scores = semantic_scores
        for s,c in zip(scores,candidates):
            c.score = float(s)
        candidates = sorted(candidates,key=lambda x: x.score,reverse=True)
        return candidates
    
    @abstractmethod
    def get_similarity_score(self, s1:list[str], s2:list[str]) -> np.ndarray:
        raise NotImplementedError

registered_rerankers = {}

def register_reranker(name:str):
    def decorator(cls):
        registered_rerankers[name] = cls
        return cls
    return decorator

def get_reranker_cls(name:str) -> Type[BaseReranker]:
    if name not in registered_rerankers:
        raise ValueError(f"Reranker {name} not found")
    return registered_rerankers[name]
