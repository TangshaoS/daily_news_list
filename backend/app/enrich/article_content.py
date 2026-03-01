"""
Article content enrichment - fetch HTML and extract main text for digest/summary.

Used during export (for top N items only) to get full article text, then compress
for LLM or extractive summary. Falls back to meta/RSS when fetch fails (paywall, 403).
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field

import httpx

from ..models import NewsItem

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 768 * 1024  # 768KB
DEFAULT_CONCURRENCY = 5
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsSummaryBot/1.0; +https://github.com/news-summary)"
)
DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

# Compression: keep first N paragraphs and cap total chars for LLM
MAX_PARAGRAPHS = 5
MAX_COMPRESSED_CHARS = 3000
# Sentence with digits or % is often key fact
HAS_NUMBER_RE = re.compile(r"\d|%")
_WS_RE = re.compile(r"\s+")


@dataclass
class ArticleContent:
    """Extracted and optionally compressed article text."""

    main_text: str = ""
    key_paragraphs: list[str] = field(default_factory=list)
    compressed_text: str = ""
    fetch_ok: bool = False


async def _stream_read_text_limited_async(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
) -> str | None:
    try:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=8192):
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            body = b"".join(chunks)
            encoding = resp.encoding or "utf-8"
            return body.decode(encoding, errors="replace")
    except Exception as e:
        logger.debug(f"article_content fetch failed for {url[:80]}...: {e}")
        return None


async def fetch_html(
    url: str,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str | None:
    """
    Fetch HTML from URL with size limit and timeout.

    Args:
        url: URL to fetch (use resolved_url when available)
        client: Optional httpx client
        max_bytes: Maximum response body size in bytes

    Returns:
        HTML string or None on failure
    """
    own_client = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": DEFAULT_ACCEPT},
            follow_redirects=True,
        )
        own_client = True

    try:
        html = await _stream_read_text_limited_async(client, url, max_bytes=max_bytes)
        return html
    finally:
        if own_client and client:
            try:
                await client.aclose()
            except Exception:
                pass


def extract_main_text(html: str) -> str:
    """
    Extract main article text from HTML using trafilatura.
    Returns clean plain text (no HTML).
    """
    if not html or len(html.strip()) < 100:
        return ""

    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        return (text or "").strip()
    except Exception as e:
        logger.debug(f"trafilatura extract failed: {e}")
        return ""


def compress_text(
    text: str,
    max_paragraphs: int = MAX_PARAGRAPHS,
    max_chars: int = MAX_COMPRESSED_CHARS,
    keep_number_sentences: bool = True,
) -> tuple[str, list[str]]:
    """
    Compress article text for LLM/summary: keep first paragraphs and sentences with numbers.

    Returns:
        (compressed_string, key_paragraphs_list)
    """
    if not text or not text.strip():
        return "", []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    key_paragraphs: list[str] = []
    seen: set[str] = set()
    total_len = 0

    # First: add paragraphs in order up to max_paragraphs
    for p in paragraphs[:max_paragraphs]:
        if total_len + len(p) > max_chars:
            break
        if p not in seen:
            key_paragraphs.append(p)
            seen.add(p)
            total_len += len(p)

    # Optionally add short sentences that contain numbers (key facts)
    if keep_number_sentences and total_len < max_chars:
        for p in paragraphs[max_paragraphs:]:
            if total_len >= max_chars:
                break
            for sent in re.split(r"[.!?。！？]+", p):
                s = _WS_RE.sub(" ", sent).strip()
                if 20 <= len(s) <= 400 and HAS_NUMBER_RE.search(s) and s not in seen:
                    key_paragraphs.append(s)
                    seen.add(s)
                    total_len += len(s)
                    if total_len >= max_chars:
                        break

    compressed = "\n\n".join(key_paragraphs)
    if len(compressed) > max_chars:
        compressed = compressed[:max_chars].rsplit(maxsplit=1)[0] + "..."

    return compressed, key_paragraphs


async def _enrich_one_content(
    item: NewsItem,
    resolved_url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[str, ArticleContent]:
    """Fetch HTML for one item, extract main text, compress. Key = normalized_url or url."""
    url_key = item.normalized_url or item.url

    async with semaphore:
        try:
            html = await fetch_html(resolved_url, client=client, max_bytes=max_bytes)
            if not html:
                return (
                    url_key,
                    ArticleContent(
                        main_text="",
                        key_paragraphs=[],
                        compressed_text=item.summary or "",
                        fetch_ok=False,
                    ),
                )

            main_text = extract_main_text(html)
            if not main_text:
                main_text = item.summary or ""

            compressed, key_paragraphs = compress_text(main_text)

            return (
                url_key,
                ArticleContent(
                    main_text=main_text,
                    key_paragraphs=key_paragraphs,
                    compressed_text=compressed or item.summary or "",
                    fetch_ok=bool(main_text),
                ),
            )
        except Exception as e:
            logger.debug(f"Article content enrich failed for {url_key[:80]}...: {e}")
            return (
                url_key,
                ArticleContent(
                    main_text="",
                    key_paragraphs=[],
                    compressed_text=item.summary or "",
                    fetch_ok=False,
                ),
            )


async def enrich_items_content(
    items: list[NewsItem],
    meta_map: dict[str, "PageMeta"] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, ArticleContent]:
    """
    Fetch and extract article content for a list of items.
    Uses resolved_url from meta_map when available, else item url.

    Args:
        items: List of NewsItem objects
        meta_map: Optional dict mapping (normalized_url or url) -> PageMeta (with resolved_url)
        concurrency: Max concurrent requests
        max_bytes: Max HTML bytes per page

    Returns:
        Dict mapping normalized_url (or url) -> ArticleContent
    """
    from .page_meta import PageMeta

    results: dict[str, ArticleContent] = {}
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": DEFAULT_ACCEPT},
        follow_redirects=True,
    ) as client:
        tasks = []
        for item in items:
            url_key = item.normalized_url or item.url
            resolved = url_key
            if meta_map and url_key in meta_map:
                meta = meta_map[url_key]
                if isinstance(meta, PageMeta) and meta.resolved_url:
                    resolved = meta.resolved_url
            tasks.append(
                _enrich_one_content(
                    item,
                    resolved,
                    client,
                    semaphore,
                    max_bytes=max_bytes,
                )
            )

        done = await asyncio.gather(*tasks, return_exceptions=True)
        for result in done:
            if isinstance(result, Exception):
                logger.warning(f"Content enrich task failed: {result}")
                continue
            key, content = result
            results[key] = content

    return results
