"""
Extractive summarization - rule-based approach using keyword/sentence scoring.

This is a lightweight, cost-free alternative to LLM summarization.
Good for MVP when you just need quick key points from RSS summaries.
"""
import logging
import re
from collections import Counter
from dataclasses import dataclass

from ..models import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class ExtractiveConfig:
    """Configuration for extractive summarization."""
    # Number of key sentences to extract
    max_sentences: int = 3
    # Minimum sentence length (characters)
    min_sentence_length: int = 20
    # Maximum sentence length (characters)
    max_sentence_length: int = 300


def _tokenize(text: str) -> list[str]:
    """Simple word tokenization."""
    # Remove punctuation and split
    words = re.findall(r'\b\w+\b', text.lower())
    return words


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitting (handles English and Chinese)
    # English: split on . ! ?
    # Chinese: split on 。！？
    sentences = re.split(r'[.!?。！？]+', text)
    return [s.strip() for s in sentences if s.strip()]


def _score_sentence(
    sentence: str,
    word_freq: Counter,
    position: int,
    total_sentences: int,
) -> float:
    """
    Score a sentence based on:
    1. Word frequency (TF-like)
    2. Position (earlier sentences often more important)
    3. Length (prefer medium-length sentences)
    """
    words = _tokenize(sentence)
    if not words:
        return 0.0
    
    # Word frequency score (average TF of words in sentence)
    freq_score = sum(word_freq.get(w, 0) for w in words) / len(words)
    
    # Position score (first sentences get bonus)
    if total_sentences > 0:
        position_score = 1.0 - (position / total_sentences) * 0.5
    else:
        position_score = 1.0
    
    # Length score (prefer 50-200 chars)
    length = len(sentence)
    if 50 <= length <= 200:
        length_score = 1.0
    elif length < 50:
        length_score = length / 50
    else:
        length_score = max(0.5, 1.0 - (length - 200) / 200)
    
    return freq_score * position_score * length_score


def extract_key_sentences(
    text: str,
    config: ExtractiveConfig | None = None,
) -> list[str]:
    """
    Extract key sentences from text using TF-based scoring.
    
    Args:
        text: Input text to summarize
        config: Optional configuration
    
    Returns:
        List of key sentences (ordered by importance)
    """
    if config is None:
        config = ExtractiveConfig()
    
    if not text or len(text) < config.min_sentence_length:
        return []
    
    # Split into sentences
    sentences = _split_sentences(text)
    
    # Filter by length
    valid_sentences = [
        (i, s) for i, s in enumerate(sentences)
        if config.min_sentence_length <= len(s) <= config.max_sentence_length
    ]
    
    if not valid_sentences:
        return []
    
    # Calculate word frequencies across all text
    all_words = _tokenize(text)
    word_freq = Counter(all_words)
    
    # Score sentences
    scored = []
    for position, sentence in valid_sentences:
        score = _score_sentence(
            sentence,
            word_freq,
            position,
            len(valid_sentences),
        )
        scored.append((score, position, sentence))
    
    # Sort by score (descending)
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Take top sentences, then reorder by original position
    top_sentences = scored[:config.max_sentences]
    top_sentences.sort(key=lambda x: x[1])  # Sort by position
    
    return [s[2] for s in top_sentences]


def extract_key_points(items: list[NewsItem], max_points: int = 5) -> list[str]:
    """
    Extract key points from a list of related news items.
    Useful for summarizing a cluster of similar stories.
    
    Args:
        items: List of NewsItem objects (typically from same cluster)
        max_points: Maximum number of points to extract
    
    Returns:
        List of key point strings
    """
    # Combine all summaries
    all_text = " ".join(item.summary for item in items if item.summary)
    
    if not all_text:
        # Fallback to titles
        return [item.title for item in items[:max_points]]
    
    # Extract sentences
    sentences = extract_key_sentences(all_text, ExtractiveConfig(max_sentences=max_points))
    
    if not sentences:
        return [item.title for item in items[:max_points]]
    
    return sentences
