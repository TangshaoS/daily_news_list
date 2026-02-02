"""
URL normalization module.
Ensures URLs are canonical and free of tracking parameters.
"""
from .url_normalizer import normalize_url, normalize_news_items

__all__ = ["normalize_url", "normalize_news_items"]
