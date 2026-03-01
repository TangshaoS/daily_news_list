"""
Summarization module - optional summary generation for news items.
Supports both rule-based (extractive) and LLM-based (generative) approaches.
"""
from .extractive import (
    extract_cluster_points,
    extract_cluster_points_for_digest,
    extract_key_points,
    extract_key_sentences,
)
from .llm_summarizer import (
    LLMSummarizer,
    refine_all_cluster_points,
    summarize_with_llm,
)

__all__ = [
    "extract_cluster_points",
    "extract_cluster_points_for_digest",
    "extract_key_points",
    "extract_key_sentences",
    "LLMSummarizer",
    "refine_all_cluster_points",
    "summarize_with_llm",
]
