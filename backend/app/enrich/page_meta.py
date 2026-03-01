"""
Page metadata enrichment - fetches HTML and extracts og:title, meta description, etc.

Used during export to augment NewsItem with page-level title/description.
Falls back to RSS data when fetch fails (paywall, 403, etc.).
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import NewsItem

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 512 * 1024  # 512KB
DEFAULT_RESOLVE_MAX_BYTES = 256 * 1024  # 256KB is enough for redirect pages
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsSummaryBot/1.0; +https://github.com/news-summary)"
)
DEFAULT_CONCURRENCY = 8
DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

GOOGLE_NEWS_HOSTS = {"news.google.com"}
GOOGLE_HOST_SUFFIXES = (".google.com", ".googleusercontent.com")
GSTATIC_HOST = "www.gstatic.com"


def _try_googlenewsdecoder(url: str) -> str | None:
    """Optional: use googlenewsdecoder when redirects land on gstatic."""
    try:
        from googlenewsdecoder import gnewsdecoder
        result = gnewsdecoder(url, interval=1)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"googlenewsdecoder failed: {e}")
    return None
_WS_RE = re.compile(r"\s+")


@dataclass
class PageMeta:
    """Extracted metadata from a news page HTML."""

    resolved_url: str = ""
    title: str = ""
    description: str = ""
    canonical_url: str | None = None
    site_name: str | None = None
    published_time: str | None = None
    fetch_ok: bool = False


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    return _WS_RE.sub(" ", s).strip()


def _is_google_news_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    return host in GOOGLE_NEWS_HOSTS


def _looks_like_external_article(url: str) -> bool:
    """Heuristic filter for candidate publisher URLs."""
    try:
        p = urlparse(url)
    except Exception:
        return False

    host = (p.hostname or "").lower()
    if not host:
        return False
    if host in GOOGLE_NEWS_HOSTS:
        return False
    if any(host.endswith(suf) for suf in GOOGLE_HOST_SUFFIXES):
        return False
    if p.scheme not in {"http", "https"}:
        return False
    # Avoid obvious non-article endpoints
    if p.path in {"", "/"}:
        return False
    return True


def _extract_meta_refresh_url(html: str, base_url: str) -> str | None:
    """Extract meta-refresh URL: <meta http-equiv="refresh" content="0; url=...">."""
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    tag = soup.find("meta", attrs={"http-equiv": re.compile(r"^refresh$", re.I)})
    content = tag.get("content") if tag else None
    if not content:
        return None

    # Common formats:
    # - "0; url=https://example.com"
    # - "5;URL=/path"
    m = re.search(r"url\s*=\s*(.+)$", content, flags=re.I)
    if not m:
        return None
    candidate = m.group(1).strip().strip("'\"")
    if not candidate:
        return None
    return urljoin(base_url, candidate)


def _extract_urls_from_value(value: str, base_url: str) -> Iterable[str]:
    """
    Extract one or more URLs from an attribute value.
    Supports:
    - direct absolute URLs
    - relative paths
    - "…?url=<encoded>" patterns
    """
    v = (value or "").strip()
    if not v:
        return []

    urls: list[str] = []

    # direct URL / relative URL
    if v.startswith(("http://", "https://", "/")):
        urls.append(urljoin(base_url, v))

    # query parameter patterns that embed a destination URL
    try:
        p = urlparse(v if v.startswith(("http://", "https://")) else urljoin(base_url, v))
        qs = parse_qs(p.query)
        for key in ("url", "u", "q"):
            if key in qs:
                for raw in qs[key]:
                    decoded = unquote(raw)
                    if decoded.startswith(("http://", "https://")):
                        urls.append(decoded)
    except Exception:
        pass

    return urls


def _extract_publisher_url_from_google_news_html(html: str, base_url: str) -> str | None:
    """
    Google News article pages often contain the publisher URL in:
    - <a ... href="..."> (sometimes relative + embedded url=)
    - data-n-au / data-n-href attributes
    - occasionally meta refresh
    """
    if not html or len(html.strip()) < 50:
        return None

    # meta-refresh is the most explicit redirect if present
    refresh = _extract_meta_refresh_url(html, base_url)
    if refresh and _looks_like_external_article(refresh):
        return refresh

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    candidates: list[str] = []

    # Common attributes that may contain publisher URL
    for tag in soup.find_all(["a", "link", "meta"]):
        for attr in ("href", "content", "data-n-au", "data-n-href"):
            val = tag.get(attr)
            if not val or not isinstance(val, str):
                continue
            candidates.extend(list(_extract_urls_from_value(val, base_url)))

    # Also scan for any absolute URLs inside the HTML as a last resort
    for m in re.finditer(r"https?://[^\s\"'<>]+", html):
        candidates.append(m.group(0))

    # Score and pick best external candidate
    best: str | None = None
    best_score = -1
    for u in candidates:
        if not _looks_like_external_article(u):
            continue
        try:
            p = urlparse(u)
        except Exception:
            continue

        score = 0
        if p.scheme == "https":
            score += 2
        # longer paths are more likely article links
        score += min(len(p.path), 120) // 20
        if p.query:
            score += 1
        # penalize obvious tracking-only redirectors
        if "google" in (p.hostname or ""):
            score -= 5

        if score > best_score:
            best_score = score
            best = u

    return best


async def _stream_read_text_limited(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
) -> tuple[str | None, httpx.Response | None]:
    """
    Stream-download up to max_bytes and decode to text.
    Returns (text, response). On failure returns (None, None).
    """
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
            try:
                return body.decode(encoding, errors="replace"), resp
            except Exception:
                return body.decode("utf-8", errors="replace"), resp
    except Exception as e:
        logger.debug(f"stream read failed for {url[:80]}...: {e}")
        return None, None


async def resolve_url(
    url: str,
    client: httpx.AsyncClient | None = None,
    max_hops: int = 5,
) -> str:
    """
    Resolve URL to final destination after following redirects.
    For Google News URLs, attempts to extract the publisher URL from the
    intermediate HTML when redirects do not directly reach the publisher.

    Args:
        url: URL to resolve (e.g. news.google.com/rss/articles/...)
        client: Optional httpx client (must have follow_redirects=True)

    Returns:
        Final URL after redirects, or original url on failure
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
        if max_hops <= 0:
            return url

        # Prefer GET for Google News (HEAD often blocked or unhelpful)
        response: httpx.Response | None = None
        if not _is_google_news_url(url):
            try:
                response = await client.head(url)
            except Exception as e:
                logger.debug(f"resolve_url HEAD failed for {url[:80]}...: {e}")

        if response is None:
            # Use a streaming read so we can parse redirect HTML safely.
            html, resp = await _stream_read_text_limited(
                client,
                url,
                max_bytes=DEFAULT_RESOLVE_MAX_BYTES,
            )
            response = resp

            if response is not None:
                resolved = str(response.url)

                # Handle meta-refresh redirects (not only Google News)
                refresh = _extract_meta_refresh_url(html or "", resolved)
                if refresh:
                    return await resolve_url(refresh, client, max_hops=max_hops - 1)

                # Google News fallback: unwrap publisher URL from HTML
                if _is_google_news_url(resolved) or _is_google_news_url(url):
                    publisher = _extract_publisher_url_from_google_news_html(
                        html or "",
                        resolved,
                    )
                    # When redirect lands on gstatic, try googlenewsdecoder
                    if not publisher and GSTATIC_HOST in resolved:
                        decoder_url = await asyncio.to_thread(_try_googlenewsdecoder, url)
                        if decoder_url and _looks_like_external_article(decoder_url):
                            publisher = decoder_url
                    if publisher:
                        # One more pass to resolve publisher redirects (if any).
                        try:
                            r2 = await client.head(publisher)
                            return str(r2.url)
                        except Exception:
                            try:
                                r2 = await client.get(publisher)
                                return str(r2.url)
                            except Exception:
                                return publisher

                return resolved

        # HEAD path for non-Google
        return str(response.url)
    except Exception as e2:
        logger.debug(f"resolve_url failed for {url[:80]}...: {e2}")
        return url
    finally:
        if own_client and client:
            try:
                await client.aclose()
            except Exception:
                pass


async def fetch_html(
    url: str,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str | None:
    """
    Fetch HTML from URL with size limit and timeout.

    Args:
        url: URL to fetch
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
        html, _ = await _stream_read_text_limited(client, url, max_bytes=max_bytes)
        return html
    except Exception as e:
        logger.debug(f"fetch_html failed for {url[:80]}...: {e}")
        return None
    finally:
        if own_client and client:
            try:
                await client.aclose()
            except Exception:
                pass


def extract_meta(html: str, fallback_url: str = "") -> PageMeta:
    """
    Extract metadata from HTML using BeautifulSoup.

    Priority:
    - title: og:title > <title> > ""
    - description: og:description > meta[name=description] > ""
    - canonical: link[rel=canonical]
    - site_name: og:site_name
    - published_time: article:published_time

    Args:
        html: Raw HTML string
        fallback_url: URL to store as resolved_url when not from fetch

    Returns:
        PageMeta with extracted fields; fetch_ok=True since we have HTML
    """
    meta = PageMeta(resolved_url=fallback_url, fetch_ok=bool(html))

    if not html or len(html.strip()) < 100:
        return meta

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.debug(f"extract_meta parse failed: {e}")
            return meta

    # og:title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        meta.title = _clean_text(og_title["content"])

    if not meta.title:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            meta.title = _clean_text(title_tag.string)

    # og:description
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        meta.description = _clean_text(og_desc["content"])

    if not meta.description:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            meta.description = _clean_text(meta_desc["content"])

    # Truncate long descriptions
    if len(meta.description) > 500:
        meta.description = meta.description[:500].rstrip() + "..."

    # link rel=canonical
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        meta.canonical_url = _clean_text(canonical["href"])

    # og:site_name
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        meta.site_name = _clean_text(og_site["content"])

    # article:published_time
    art_pub = soup.find("meta", property="article:published_time")
    if art_pub and art_pub.get("content"):
        meta.published_time = _clean_text(art_pub["content"])

    return meta


async def _enrich_one(
    item: NewsItem,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> tuple[str, PageMeta]:
    """
    Enrich a single NewsItem: resolve URL, fetch HTML, extract meta.
    Uses item.url or item.normalized_url as input.
    """
    url = item.normalized_url or item.url
    key = url

    async with semaphore:
        try:
            resolved = await resolve_url(url, client)
            html = await fetch_html(resolved, client)
            meta = extract_meta(html or "", fallback_url=resolved)
            meta.resolved_url = resolved

            # Apply fallbacks for title/description from RSS
            if not meta.title and item.title:
                meta.title = item.title
            if not meta.description and item.summary:
                meta.description = item.summary

            return (key, meta)
        except Exception as e:
            logger.debug(f"Enrich failed for {url[:80]}...: {e}")
            fallback = PageMeta(
                resolved_url=url,
                title=item.title,
                description=item.summary,
                fetch_ok=False,
            )
            return (key, fallback)


async def enrich_items(
    items: list[NewsItem],
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict[str, PageMeta]:
    """
    Enrich a list of NewsItems with page metadata (title, description, etc.).

    Args:
        items: List of NewsItem objects
        concurrency: Max concurrent requests (default 8)

    Returns:
        Dict mapping normalized_url (or url) to PageMeta
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, PageMeta] = {}

    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    ) as client:
        tasks = [_enrich_one(item, client, semaphore) for item in items]
        done = await asyncio.gather(*tasks, return_exceptions=True)

        for result in done:
            if isinstance(result, Exception):
                logger.warning(f"Enrich task failed: {result}")
                continue
            key, meta = result
            results[key] = meta

    return results
