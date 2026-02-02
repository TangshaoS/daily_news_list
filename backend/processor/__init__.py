"""News processing module"""
from .classifier import NewsClassifier
from .summarizer import Summarizer, LLMSummarizer, ExtractiveSummarizer

__all__ = ["NewsClassifier", "Summarizer", "LLMSummarizer", "ExtractiveSummarizer"]
