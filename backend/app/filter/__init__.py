"""
Topic filtering module - filters news by relevance to target topics.
"""
from .topic_filter import TopicFilter, filter_by_topics

__all__ = ["TopicFilter", "filter_by_topics"]
