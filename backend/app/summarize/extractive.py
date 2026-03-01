"""
Extractive summarization - rule-based approach using keyword/sentence scoring.

This is a lightweight, cost-free alternative to LLM summarization.
Good for MVP when you just need quick key points from RSS summaries.
Supports cluster-level key points by aggregating multiple sources per cluster.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

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


def _build_item_summary_text(
    item: NewsItem,
    meta_map: dict[str, Any] | None = None,
    content_map: dict[str, list[str]] | None = None,
) -> str:
    """
    Build a single "clean summary" string for one item: meta description or RSS summary,
    plus optional key paragraphs. Used when aggregating cluster content.
    """
    url = item.normalized_url or item.url
    parts: list[str] = []

    # Prefer meta description, fallback to RSS summary
    description = ""
    if meta_map and url in meta_map:
        meta = meta_map[url]
        description = getattr(meta, "description", None) or ""
    if not description and item.summary:
        description = item.summary
    if description:
        parts.append(description.strip())

    # Append key paragraphs if available
    if content_map and url in content_map:
        for p in content_map[url]:
            if p and p.strip():
                parts.append(p.strip())

    return " ".join(parts) if parts else ""


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


def extract_cluster_points(
    items: list[NewsItem],
    meta_map: dict[str, Any] | None = None,
    content_map: dict[str, list[str]] | None = None,
    max_points: int = 5,
) -> list[str]:
    """
    Extract key points for a single cluster by aggregating multi-source content.

    Builds a combined text from each item's meta description (or RSS summary) and
    optional key paragraphs, then runs extractive sentence selection to produce
    3–7 key points. Use when you have enriched meta/content per URL.

    Args:
        items: List of NewsItem objects in the same cluster.
        meta_map: Optional URL -> object with .description (e.g. PageMeta).
        content_map: Optional URL -> list of key paragraph strings.
        max_points: Maximum number of points (default 5; plan suggests 3–7).

    Returns:
        List of key point strings for this cluster.
    """
    if not items:
        return []

    combined_parts: list[str] = []
    for item in items:
        text = _build_item_summary_text(item, meta_map=meta_map, content_map=content_map)
        if text:
            combined_parts.append(text)

    all_text = " ".join(combined_parts)
    if not all_text:
        return [item.title for item in items[:max_points]]

    sentences = extract_key_sentences(
        all_text, ExtractiveConfig(max_sentences=max_points)
    )
    if not sentences:
        return [item.title for item in items[:max_points]]

    return sentences


def extract_cluster_points_for_digest(
    items: list[NewsItem],
    meta_map: dict[str, Any] | None = None,
    content_map: dict[str, list[str]] | None = None,
    max_points: int = 5,
) -> dict[str, list[str]]:
    """
    Produce cluster_id -> list of key points for all clusters in the item list.

    Groups items by cluster_id (or normalized_url/url as fallback), then runs
    extract_cluster_points on each group. Use this to fill cluster_points when
    exporting digest JSON.

    Args:
        items: Full list of items (will be grouped by cluster_id).
        meta_map: Optional URL -> object with .description.
        content_map: Optional URL -> list of key paragraph strings.
        max_points: Max points per cluster (default 5).

    Returns:
        Dict mapping cluster_id to list of key point strings.
    """
    clusters: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        cid = item.cluster_id or (item.normalized_url or item.url)
        clusters[cid].append(item)

    result: dict[str, list[str]] = {}
    for cid, cluster_items in clusters.items():
        result[cid] = extract_cluster_points(
            cluster_items,
            meta_map=meta_map,
            content_map=content_map,
            max_points=max_points,
        )
    return result
