"""
Deduplication and clustering for news items.
"""
import hashlib
import logging
from collections import defaultdict

from rapidfuzz import fuzz

from ..models import NewsItem

logger = logging.getLogger(__name__)

# Similarity threshold for clustering (0-100)
TITLE_SIMILARITY_THRESHOLD = 75


def deduplicate_items(items: list[NewsItem]) -> list[NewsItem]:
    """
    Remove exact URL duplicates, keeping the first occurrence.
    
    Args:
        items: List of NewsItem objects
    
    Returns:
        Deduplicated list
    """
    seen_urls: set[str] = set()
    unique_items: list[NewsItem] = []
    
    for item in items:
        # Use normalized URL if available
        url_key = item.normalized_url or item.url
        
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            unique_items.append(item)
    
    removed = len(items) - len(unique_items)
    if removed > 0:
        logger.info(f"Removed {removed} duplicate URLs")
    
    return unique_items


def _generate_cluster_id(title: str) -> str:
    """Generate a cluster ID from a title."""
    return hashlib.md5(title.lower().encode()).hexdigest()[:12]


def cluster_similar_items(
    items: list[NewsItem],
    similarity_threshold: int = TITLE_SIMILARITY_THRESHOLD,
) -> list[NewsItem]:
    """
    Cluster news items by title similarity.
    Items covering the same story from different sources get grouped.
    
    This helps identify "hot" stories (covered by multiple sources)
    and prevents showing the same story multiple times.
    
    Args:
        items: List of NewsItem objects
        similarity_threshold: Minimum similarity score (0-100) to cluster
    
    Returns:
        Items with cluster_id and cluster_size populated
    """
    if not items:
        return items
    
    # Track clusters: cluster_id -> list of item indices
    clusters: dict[str, list[int]] = defaultdict(list)
    item_to_cluster: dict[int, str] = {}
    
    # Simple O(n²) clustering - acceptable for MVP scale
    for i, item in enumerate(items):
        if i in item_to_cluster:
            continue
        
        # Start a new cluster
        cluster_id = _generate_cluster_id(item.title)
        clusters[cluster_id].append(i)
        item_to_cluster[i] = cluster_id
        
        # Find similar items
        for j, other in enumerate(items[i + 1:], start=i + 1):
            if j in item_to_cluster:
                continue
            
            # Compare titles using token sort ratio (handles word order differences)
            similarity = fuzz.token_sort_ratio(
                item.title.lower(),
                other.title.lower(),
            )
            
            if similarity >= similarity_threshold:
                clusters[cluster_id].append(j)
                item_to_cluster[j] = cluster_id
    
    # Update items with cluster info
    for cluster_id, indices in clusters.items():
        cluster_size = len(indices)
        
        # Collect unique sources in this cluster
        sources_in_cluster = set(items[i].source_id for i in indices)
        
        for idx in indices:
            items[idx].cluster_id = cluster_id
            # Use number of unique sources as cluster_size (more meaningful for scoring)
            items[idx].cluster_size = len(sources_in_cluster)
    
    # Log clustering stats
    multi_source_clusters = sum(1 for c in clusters.values() if len(set(items[i].source_id for i in c)) > 1)
    logger.info(
        f"Created {len(clusters)} clusters, {multi_source_clusters} with multiple sources"
    )
    
    return items


def get_cluster_representatives(items: list[NewsItem]) -> list[NewsItem]:
    """
    Get one representative item per cluster.
    Picks the item from the highest-weighted source.
    
    Useful for final export to avoid showing duplicate stories.
    
    Args:
        items: Clustered NewsItem list
    
    Returns:
        List with one item per cluster
    """
    clusters: dict[str, list[NewsItem]] = defaultdict(list)
    
    for item in items:
        cluster_id = item.cluster_id or item.normalized_url or item.url
        clusters[cluster_id].append(item)
    
    representatives = []
    for cluster_items in clusters.values():
        # Sort by source weight (descending), then by recency
        cluster_items.sort(
            key=lambda x: (x.source_weight, x.published_at or x.fetched_at),
            reverse=True,
        )
        # Keep the best representative but preserve cluster_size
        best = cluster_items[0]
        representatives.append(best)
    
    logger.info(f"Selected {len(representatives)} cluster representatives from {len(items)} items")
    return representatives
