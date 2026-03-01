"""
NotebookLM export - generates URL lists for import into Google NotebookLM.

Supported output formats:
1. Plain URL list (one URL per line) - for direct paste into NotebookLM
2. Markdown list (with titles and metadata) - for human-readable reference
3. JSON export (full metadata) - for programmatic use
4. Digest JSON (clusters + by_category) - for daily digest / frontend
"""
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from ..enrich.page_meta import PageMeta
from ..models import Category, ExportResult, NewsItem
from ..sources import get_source
from ..summarize.extractive import extract_cluster_points_for_digest

logger = logging.getLogger(__name__)

# NotebookLM has a limit of 50 sources per notebook
NOTEBOOKLM_SOURCE_LIMIT = 50

# Default export directory
DEFAULT_EXPORT_DIR = Path("exports")

# Digest display limits: avoid dumping raw HTML or huge text into JSON/frontend
DIGEST_DESCRIPTION_MAX_CHARS = 500
DIGEST_KEY_PARAGRAPH_MAX_CHARS = 600
DIGEST_KEY_PARAGRAPHS_MAX_COUNT = 5
DIGEST_POINT_MAX_CHARS = 280


def _strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if not text or not isinstance(text, str):
        return ""
    s = re.sub(r"<[^>]+>", "", text)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _truncate(text: str, max_chars: int, suffix: str = "...") -> str:
    """Truncate to max_chars, adding suffix if cut."""
    if not text or len(text) <= max_chars:
        return text or ""
    return text[: max_chars - len(suffix)].rstrip() + suffix


class NotebookLMExporter:
    """
    Exports news items in formats suitable for NotebookLM import.
    """
    
    def __init__(self, export_dir: Path | str = DEFAULT_EXPORT_DIR):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_filename(self, prefix: str, extension: str) -> str:
        """Generate a timestamped filename."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}.{extension}"
    
    @staticmethod
    def _write_urls_grouped(
        f: TextIO,
        urls: list[str],
        group_size: int = 10,
    ) -> None:
        """
        Write URLs line-by-line, inserting a blank line every `group_size` URLs.
        
        This matches workflows where NotebookLM is used to import in batches (e.g., 10 at a time).
        Set group_size <= 0 to disable grouping.
        """
        if group_size <= 0:
            for url in urls:
                f.write(f"{url}\n")
            return
        
        for idx, url in enumerate(urls, start=1):
            f.write(f"{url}\n")
            if idx % group_size == 0 and idx != len(urls):
                f.write("\n")
    
    def export_urls_plain(
        self,
        items: list[NewsItem],
        filename: str | None = None,
        limit: int = NOTEBOOKLM_SOURCE_LIMIT,
        group_size: int = 10,
    ) -> ExportResult:
        """
        Export URLs as a plain text file (one URL per line).
        This format can be directly pasted into NotebookLM's "Add Source" dialog.
        
        Args:
            items: List of NewsItem objects (should be pre-sorted by score)
            filename: Optional custom filename
            limit: Maximum number of URLs to export
            group_size: Insert a blank line every N URLs (default 10). Use <=0 to disable.
        
        Returns:
            ExportResult with file path and metadata
        """
        if filename is None:
            filename = self._generate_filename("notebooklm_urls", "txt")
        
        filepath = self.export_dir / filename
        
        # Limit items
        export_items = items[:limit]
        
        # Collect unique URLs (prefer normalized)
        urls = []
        seen = set()
        for item in export_items:
            url = item.normalized_url or item.url
            if url not in seen:
                urls.append(url)
                seen.add(url)
        
        # Write file
        with open(filepath, "w", encoding="utf-8") as f:
            self._write_urls_grouped(f, urls, group_size=group_size)
        
        # Collect categories
        all_categories = set()
        for item in export_items:
            all_categories.update(item.categories)
        
        logger.info(f"Exported {len(urls)} URLs to {filepath}")
        
        return ExportResult(
            filepath=str(filepath),
            url_count=len(urls),
            categories=list(all_categories),
        )
    
    def export_urls_markdown(
        self,
        items: list[NewsItem],
        filename: str | None = None,
        limit: int = NOTEBOOKLM_SOURCE_LIMIT,
        include_metadata: bool = True,
        group_size: int = 10,
    ) -> ExportResult:
        """
        Export as a Markdown file with titles and optional metadata.
        Useful for human-readable reference and archiving.
        
        Args:
            items: List of NewsItem objects (should be pre-sorted by score)
            filename: Optional custom filename
            limit: Maximum number of items to export
            include_metadata: Include score, source, time info
            group_size: Insert a blank line every N URLs in the copy-paste block (default 10).
        
        Returns:
            ExportResult with file path and metadata
        """
        if filename is None:
            filename = self._generate_filename("notebooklm_news", "md")
        
        filepath = self.export_dir / filename
        
        # Limit items
        export_items = items[:limit]
        
        with open(filepath, "w", encoding="utf-8") as f:
            # Header
            f.write("# News Summary Export\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total items: {len(export_items)}\n\n")
            
            # Group by category
            by_category: dict[Category, list[NewsItem]] = {}
            for item in export_items:
                for cat in item.categories:
                    if cat not in by_category:
                        by_category[cat] = []
                    by_category[cat].append(item)
            
            # Category display names
            category_names = {
                Category.GEOPOLITICS: "地缘政治 (Geopolitics)",
                Category.ECONOMY: "经济数据与货币政策 (Economy)",
                Category.MARKETS: "投资市场情绪 (Markets)",
                Category.SUPPLY_CHAIN: "供应链 (Supply Chain)",
                Category.COMMODITIES: "大宗商品 (Commodities)",
                Category.AI_TECH: "AI与科技 (AI & Tech)",
                Category.ENERGY_INFRA: "能源基础设施 (Energy & Power)",
                Category.OTHER: "其他 (Other)",
            }
            
            # Write by category
            for cat in [Category.GEOPOLITICS, Category.ECONOMY, Category.MARKETS,
                       Category.SUPPLY_CHAIN, Category.COMMODITIES, Category.AI_TECH,
                       Category.ENERGY_INFRA]:
                cat_items = by_category.get(cat, [])
                if not cat_items:
                    continue
                
                f.write(f"## {category_names.get(cat, cat.value)}\n\n")
                
                # Deduplicate within category (item might appear in multiple categories)
                seen_urls = set()
                for item in cat_items:
                    url = item.normalized_url or item.url
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    self._write_item_markdown(f, item, include_metadata)
                
                f.write("\n")
            
            # Plain URL list section (for easy copy-paste)
            f.write("---\n\n")
            f.write("## URLs for NotebookLM Import\n\n")
            f.write("Copy the URLs below and paste into NotebookLM's 'Add Source' dialog:\n\n")
            f.write("```\n")
            seen_urls = set()
            urls_for_copy: list[str] = []
            for item in export_items:
                url = item.normalized_url or item.url
                if url not in seen_urls:
                    urls_for_copy.append(url)
                    seen_urls.add(url)
            self._write_urls_grouped(f, urls_for_copy, group_size=group_size)
            f.write("```\n")
        
        # Collect categories
        all_categories = set()
        for item in export_items:
            all_categories.update(item.categories)
        
        logger.info(f"Exported {len(export_items)} items to {filepath}")
        
        return ExportResult(
            filepath=str(filepath),
            url_count=len(export_items),
            categories=list(all_categories),
        )
    
    def _write_item_markdown(
        self,
        f: TextIO,
        item: NewsItem,
        include_metadata: bool,
    ):
        """Write a single item in Markdown format."""
        url = item.normalized_url or item.url
        
        # Get source display name
        source_config = get_source(item.source_id)
        source_name = source_config.name_zh if source_config else item.source_id
        
        # Format published time
        time_str = ""
        if item.published_at:
            time_str = item.published_at.strftime("%m-%d %H:%M")
        
        # Write entry
        f.write(f"- [{item.title}]({url})")
        
        if include_metadata:
            meta_parts = []
            if source_name:
                meta_parts.append(source_name)
            if time_str:
                meta_parts.append(time_str)
            if item.final_score > 0:
                meta_parts.append(f"score: {item.final_score:.2f}")
            if item.cluster_size > 1:
                meta_parts.append(f"{item.cluster_size}源报道")
            
            if meta_parts:
                f.write(f" ({', '.join(meta_parts)})")
        
        f.write("\n")
    
    def export_json(
        self,
        items: list[NewsItem],
        filename: str | None = None,
        limit: int = NOTEBOOKLM_SOURCE_LIMIT,
        meta_map: dict[str, PageMeta] | None = None,
    ) -> ExportResult:
        """
        Export as JSON file with full metadata.
        Useful for programmatic use or debugging.

        When meta_map is provided (from page metadata enrichment), output uses
        enriched fields: input_url, resolved_url, title, description,
        canonical_url, site_name, published_time.

        Args:
            items: List of NewsItem objects
            filename: Optional custom filename
            limit: Maximum number of items to export
            meta_map: Optional dict mapping url to PageMeta (from enrich_items)
        
        Returns:
            ExportResult with file path and metadata
        """
        if filename is None:
            filename = self._generate_filename("notebooklm_data", "json")
        
        filepath = self.export_dir / filename
        
        # Limit items
        export_items = items[:limit]
        
        if meta_map:
            # Enriched format: input_url, resolved_url, title, description, etc.
            enriched_items = []
            for item in export_items:
                url = item.normalized_url or item.url
                meta = meta_map.get(url)
                if meta:
                    enriched_items.append({
                        "input_url": url,
                        "resolved_url": meta.resolved_url,
                        "title": meta.title or item.title,
                        "description": meta.description or item.summary,
                        "canonical_url": meta.canonical_url,
                        "site_name": meta.site_name,
                        "published_time": meta.published_time or (
                            item.published_at.isoformat() if item.published_at else None
                        ),
                        "source_id": item.source_id,
                        "categories": [c.value for c in item.categories],
                        "final_score": item.final_score,
                        "cluster_size": item.cluster_size,
                    })
                else:
                    # Fallback: no meta, use item fields
                    enriched_items.append({
                        "input_url": url,
                        "resolved_url": url,
                        "title": item.title,
                        "description": item.summary,
                        "canonical_url": None,
                        "site_name": None,
                        "published_time": item.published_at.isoformat() if item.published_at else None,
                        "source_id": item.source_id,
                        "categories": [c.value for c in item.categories],
                        "final_score": item.final_score,
                        "cluster_size": item.cluster_size,
                    })
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "item_count": len(enriched_items),
                "enriched": True,
                "items": enriched_items,
            }
        else:
            # Original format (no enrichment)
            data = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "item_count": len(export_items),
                "items": [
                    {
                        "url": item.normalized_url or item.url,
                        "title": item.title,
                        "summary": item.summary,
                        "source_id": item.source_id,
                        "published_at": item.published_at.isoformat() if item.published_at else None,
                        "categories": [c.value for c in item.categories],
                        "final_score": item.final_score,
                        "cluster_size": item.cluster_size,
                    }
                    for item in export_items
                ],
            }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Collect categories
        all_categories = set()
        for item in export_items:
            all_categories.update(item.categories)
        
        logger.info(f"Exported {len(export_items)} items to {filepath}")
        
        return ExportResult(
            filepath=str(filepath),
            url_count=len(export_items),
            categories=list(all_categories),
        )

    def export_digest_json(
        self,
        items: list[NewsItem],
        meta_map: dict[str, PageMeta] | None = None,
        content_map: dict[str, list[str]] | None = None,
        cluster_points: dict[str, list[str]] | None = None,
        limit_clusters: int = 50,
        filename: str | None = None,
    ) -> ExportResult:
        """
        Export digest JSON: clusters + by_category for frontend / daily digest.

        Groups items by cluster_id, keeps top clusters by score, and writes
        digest_YYYYMMDD.json plus latest_digest.json (symlink-friendly copy).

        Args:
            items: All items to consider (will be grouped by cluster_id).
            meta_map: Optional URL -> PageMeta for enriched item fields.
            content_map: Optional URL -> list of key_paragraphs (for future use).
            cluster_points: Optional cluster_id -> list of point strings.
            limit_clusters: Max number of clusters to include.
            filename: Optional custom filename (without path).

        Returns:
            ExportResult with filepath and counts.
        """
        content_map = content_map or {}
        cluster_points = cluster_points or {}

        # Group by cluster_id (or normalized_url if no cluster_id)
        clusters_raw: dict[str, list[NewsItem]] = defaultdict(list)
        for item in items:
            cid = item.cluster_id or (item.normalized_url or item.url)
            clusters_raw[cid].append(item)

        # Sort each cluster by score (desc), then take top limit_clusters by best score in cluster
        cluster_list: list[list[NewsItem]] = []
        for cid, cluster_items in clusters_raw.items():
            cluster_items.sort(key=lambda x: (x.final_score, x.published_at or x.fetched_at), reverse=True)
            cluster_list.append(cluster_items)

        cluster_list.sort(
            key=lambda cl: (cl[0].final_score if cl else 0, cl[0].published_at or cl[0].fetched_at),
            reverse=True,
        )
        cluster_list = cluster_list[:limit_clusters]

        # Build by_category: category -> [cluster_id, ...]
        by_category: dict[str, list[str]] = defaultdict(list)
        clusters_payload: list[dict] = []
        total_items = 0

        for cluster_items in cluster_list:
            if not cluster_items:
                continue
            rep = cluster_items[0]
            cid = rep.cluster_id or (rep.normalized_url or rep.url)
            categories = set()
            for it in cluster_items:
                categories.update(c.value for c in it.categories)

            headline = rep.title
            raw_points = cluster_points.get(cid, [])
            points = [
                _truncate(_strip_html(p), DIGEST_POINT_MAX_CHARS)
                for p in (raw_points if isinstance(raw_points, list) else [])
            ]

            item_payloads = []
            for item in cluster_items:
                url = item.normalized_url or item.url
                meta = meta_map.get(url) if meta_map else None
                raw_desc = (meta.description if meta else None) or item.summary or ""
                desc = _truncate(_strip_html(raw_desc), DIGEST_DESCRIPTION_MAX_CHARS)
                published_at = item.published_at.isoformat() if item.published_at else None
                resolved = (meta.resolved_url if meta else None) or url
                raw_kp = content_map.get(url, [])
                if not isinstance(raw_kp, list):
                    raw_kp = []
                key_paragraphs = [
                    _truncate(_strip_html(str(p)), DIGEST_KEY_PARAGRAPH_MAX_CHARS)
                    for p in raw_kp[:DIGEST_KEY_PARAGRAPHS_MAX_COUNT]
                ]

                item_payloads.append({
                    "title": (meta.title if meta else None) or item.title,
                    "input_url": url,
                    "resolved_url": resolved,
                    "source_id": item.source_id,
                    "published_at": published_at,
                    "description": desc,
                    "key_paragraphs": key_paragraphs,
                })
                total_items += 1

            clusters_payload.append({
                "cluster_id": cid,
                "category": sorted(categories),
                "headline": headline,
                "points": points,
                "items": item_payloads,
            })
            for cat in categories:
                by_category[cat].append(cid)

        # Deduplicate by_category cluster_id lists (cluster can be in multiple cats)
        for cat in by_category:
            by_category[cat] = list(dict.fromkeys(by_category[cat]))

        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "item_count": total_items,
            "clusters": clusters_payload,
            "by_category": dict(by_category),
        }

        if filename is None:
            filename = self._generate_filename("digest", "json")
        filepath = self.export_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Write latest_digest.json for frontend to load a fixed path
        latest_path = self.export_dir / "latest_digest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        all_categories = set()
        for item in items:
            all_categories.update(item.categories)

        logger.info(
            "Exported digest to %s and %s (%d clusters, %d items)",
            filepath,
            latest_path,
            len(clusters_payload),
            total_items,
        )
        return ExportResult(
            filepath=str(filepath),
            url_count=total_items,
            categories=list(all_categories),
        )


def export_for_notebooklm(
    items: list[NewsItem],
    export_dir: Path | str = DEFAULT_EXPORT_DIR,
    limit: int = NOTEBOOKLM_SOURCE_LIMIT,
    formats: list[str] | None = None,
    group_size: int = 10,
    meta_map: dict[str, PageMeta] | None = None,
    content_map: dict[str, list[str]] | None = None,
    digest_items: list[NewsItem] | None = None,
    limit_clusters: int = 50,
    cluster_points: dict[str, list[str]] | None = None,
) -> list[ExportResult]:
    """
    Convenience function to export news items for NotebookLM.

    Args:
        items: List of NewsItem objects (should be pre-sorted by score; used for txt/md/json).
        export_dir: Directory to write export files.
        limit: Maximum number of items to export (txt/md/json).
        formats: List of formats: "txt", "md", "json", "digest". Defaults to ["txt", "md"].
        group_size: Insert a blank line every N URLs in copy-paste outputs (default 10).
        meta_map: Optional dict from enrich_items for enriched JSON / digest export.
        content_map: Optional URL -> key_paragraphs for digest cluster points.
        digest_items: Optional full item list for digest (grouped by cluster). If None and
            "digest" in formats, uses items (may yield one item per cluster).
        limit_clusters: Max clusters in digest output (default 50).
        cluster_points: Optional precomputed cluster_id -> list of point strings (e.g. from
            extract_cluster_points_for_digest or LLM-refined). When provided and digest is in
            formats, this is used instead of computing points internally.

    Returns:
        List of ExportResult objects (one per format).
    """
    if formats is None:
        formats = ["txt", "md"]

    exporter = NotebookLMExporter(export_dir)
    results = []

    if "txt" in formats:
        results.append(exporter.export_urls_plain(items, limit=limit, group_size=group_size))

    if "md" in formats:
        results.append(exporter.export_urls_markdown(items, limit=limit, group_size=group_size))

    if "json" in formats:
        results.append(exporter.export_json(items, limit=limit, meta_map=meta_map))

    if "digest" in formats:
        source = digest_items if digest_items is not None else items
        points_to_use = cluster_points
        if points_to_use is None:
            points_to_use = extract_cluster_points_for_digest(
                source,
                meta_map=meta_map,
                content_map=content_map,
                max_points=5,
            )
        results.append(
            exporter.export_digest_json(
                source,
                meta_map=meta_map,
                content_map=content_map,
                cluster_points=points_to_use,
                limit_clusters=limit_clusters,
            )
        )

    return results
