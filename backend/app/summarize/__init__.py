"""
Summarization module - optional summary generation for news items.
Supports both rule-based (extractive) and LLM-based (generative) approaches.
"""
from .extractive import extract_key_sentences
from .llm_summarizer import LLMSummarizer, summarize_with_llm

__all__ = [
    "extract_key_sentences",
    "LLMSummarizer",
    "summarize_with_llm",
]
