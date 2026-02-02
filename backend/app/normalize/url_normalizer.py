"""
URL normalizer - canonicalizes URLs and removes tracking parameters.
"""
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ..models import NewsItem

logger = logging.getLogger(__name__)

# Common tracking parameters to remove
TRACKING_PARAMS = {
    # Google Analytics
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "gclsrc",
    # Facebook
    "fbclid", "fb_action_ids", "fb_action_types", "fb_source", "fb_ref",
    # Twitter/X
    "twclid",
    # Microsoft
    "msclkid",
    # Adobe
    "s_kwcid",
    # General tracking
    "ref", "source", "mc_cid", "mc_eid",
    # News specific
    "mod", "ns_mchannel", "ns_source", "ns_campaign", "ns_linkname",
    # Google News
    "oc", "ved", "usg",
}

# Parameters to keep for certain domains (they affect content)
KEEP_PARAMS_BY_DOMAIN = {
    "reuters.com": {"articleId"},
    "bloomberg.com": {"sref"},
}


def normalize_url(url: str) -> str:
    """
    Normalize a URL by:
    1. Lowercasing the scheme and host
    2. Removing tracking parameters
    3. Removing fragments
    4. Sorting remaining query parameters
    5. Removing trailing slashes (except for root)
    
    Args:
        url: The URL to normalize
    
    Returns:
        Normalized URL string
    """
    if not url:
        return url
    
    try:
        parsed = urlparse(url)
    except Exception:
        logger.warning(f"Failed to parse URL: {url}")
        return url
    
    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    # Remove www. prefix for consistency
    if netloc.startswith("www."):
        netloc = netloc[4:]
    
    # Get domain for domain-specific rules
    domain = netloc.split(":")[0]  # Remove port if present
    
    # Filter query parameters
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=False)
        keep_params = KEEP_PARAMS_BY_DOMAIN.get(domain, set())
        
        filtered_params = {
            k: v for k, v in params.items()
            if k.lower() not in TRACKING_PARAMS or k in keep_params
        }
        
        # Sort and rebuild query string
        sorted_params = sorted(filtered_params.items())
        query = urlencode(sorted_params, doseq=True)
    else:
        query = ""
    
    # Remove fragment
    fragment = ""
    
    # Clean path
    path = parsed.path
    # Remove trailing slash (but keep root path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    
    # Rebuild URL
    normalized = urlunparse((scheme, netloc, path, "", query, fragment))
    
    return normalized


def extract_canonical_from_google_news(url: str) -> str:
    """
    Extract the actual article URL from a Google News redirect URL.
    
    Google News URLs look like:
    https://news.google.com/rss/articles/...?oc=5
    
    The actual URL is encoded in the path or requires following the redirect.
    For now, we keep the Google News URL as-is since it will redirect.
    """
    # Google News URLs are tricky - they encode the destination
    # For MVP, we'll keep them as-is; NotebookLM should follow redirects
    return url


def normalize_news_items(items: list[NewsItem]) -> list[NewsItem]:
    """
    Normalize URLs for a list of NewsItem objects.
    
    Args:
        items: List of NewsItem objects
    
    Returns:
        Same list with normalized_url field populated
    """
    for item in items:
        # Handle Google News URLs specially
        if "news.google.com" in item.url:
            item.normalized_url = extract_canonical_from_google_news(item.url)
        else:
            item.normalized_url = normalize_url(item.url)
    
    return items
