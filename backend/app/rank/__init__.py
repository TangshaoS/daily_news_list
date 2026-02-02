"""
Ranking module - scores and sorts news items by hotness/relevance.
"""
from .ranker import HotnessRanker, rank_items

__all__ = ["HotnessRanker", "rank_items"]
