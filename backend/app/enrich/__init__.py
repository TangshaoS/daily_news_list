"""
Enrichment module - fetches page metadata and article content from news URLs.
"""
from .article_content import (
    ArticleContent,
    compress_text,
    enrich_items_content,
    extract_main_text,
    fetch_html as fetch_html_content,
)
from .page_meta import (
    PageMeta,
    extract_meta,
    enrich_items,
    resolve_url,
)

__all__ = [
    "ArticleContent",
    "PageMeta",
    "compress_text",
    "enrich_items",
    "enrich_items_content",
    "extract_main_text",
    "extract_meta",
    "fetch_html_content",
    "resolve_url",
]
