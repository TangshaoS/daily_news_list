"""
News source configurations.
Each source defines its RSS feeds, weight, and parsing hints.
"""
from .registry import SOURCE_REGISTRY, get_source, get_all_sources

__all__ = ["SOURCE_REGISTRY", "get_source", "get_all_sources"]
