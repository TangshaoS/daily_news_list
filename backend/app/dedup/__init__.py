"""
Deduplication module - removes duplicate URLs and clusters similar stories.
"""
from .deduplicator import deduplicate_items, cluster_similar_items

__all__ = ["deduplicate_items", "cluster_similar_items"]
