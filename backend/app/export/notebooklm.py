"""
NotebookLM export - generates URL lists for import into Google NotebookLM.

Supported output formats:
1. Plain URL list (one URL per line) - for direct paste into NotebookLM
2. Markdown list (with titles and metadata) - for human-readable reference
3. JSON export (full metadata) - for programmatic use
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from ..models import Category, ExportResult, NewsItem
from ..sources import get_source

logger = logging.getLogger(__name__)

# NotebookLM has a limit of 50 sources per notebook
NOTEBOOKLM_SOURCE_LIMIT = 50

# Default export directory
DEFAULT_EXPORT_DIR = Path("exports")


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
    
    def export_urls_plain(
        self,
        items: list[NewsItem],
        filename: str | None = None,
        limit: int = NOTEBOOKLM_SOURCE_LIMIT,
    ) -> ExportResult:
        """
        Export URLs as a plain text file (one URL per line).
        This format can be directly pasted into NotebookLM's "Add Source" dialog.
        
        Args:
            items: List of NewsItem objects (should be pre-sorted by score)
            filename: Optional custom filename
            limit: Maximum number of URLs to export
        
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
            for url in urls:
                f.write(f"{url}\n")
        
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
    ) -> ExportResult:
        """
        Export as a Markdown file with titles and optional metadata.
        Useful for human-readable reference and archiving.
        
        Args:
            items: List of NewsItem objects (should be pre-sorted by score)
            filename: Optional custom filename
            limit: Maximum number of items to export
            include_metadata: Include score, source, time info
        
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
            for item in export_items:
                url = item.normalized_url or item.url
                if url not in seen_urls:
                    f.write(f"{url}\n")
                    seen_urls.add(url)
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
    ) -> ExportResult:
        """
        Export as JSON file with full metadata.
        Useful for programmatic use or debugging.
        
        Args:
            items: List of NewsItem objects
            filename: Optional custom filename
            limit: Maximum number of items to export
        
        Returns:
            ExportResult with file path and metadata
        """
        if filename is None:
            filename = self._generate_filename("notebooklm_data", "json")
        
        filepath = self.export_dir / filename
        
        # Limit items
        export_items = items[:limit]
        
        # Convert to serializable format
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


def export_for_notebooklm(
    items: list[NewsItem],
    export_dir: Path | str = DEFAULT_EXPORT_DIR,
    limit: int = NOTEBOOKLM_SOURCE_LIMIT,
    formats: list[str] | None = None,
) -> list[ExportResult]:
    """
    Convenience function to export news items for NotebookLM.
    
    Args:
        items: List of NewsItem objects (should be pre-sorted by score)
        export_dir: Directory to write export files
        limit: Maximum number of items to export
        formats: List of formats to export ("txt", "md", "json"). 
                 Defaults to ["txt", "md"].
    
    Returns:
        List of ExportResult objects (one per format)
    """
    if formats is None:
        formats = ["txt", "md"]
    
    exporter = NotebookLMExporter(export_dir)
    results = []
    
    if "txt" in formats:
        results.append(exporter.export_urls_plain(items, limit=limit))
    
    if "md" in formats:
        results.append(exporter.export_urls_markdown(items, limit=limit))
    
    if "json" in formats:
        results.append(exporter.export_json(items, limit=limit))
    
    return results
