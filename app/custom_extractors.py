"""
Custom extractors for anime grabber.

Define functions here for custom extraction logic.
Each function should match the signature expected by the grabber.

For extract_latest: def func(html, base_url=None) -> dict with "link" and "title"
For extract_download: def func(html) -> dict with "link", "host", "quality"
"""

import re
from urllib.parse import urljoin

def extract_latest_custom(html, base_url=None):
    """Custom extractor for latest episode link and title."""
    # Example: find first <a> with href containing 'episode'
    m = re.search(r'<a\s+href="([^"]*episode[^"]*)"[^>]*>([^<]+)</a>', html, re.I)
    if not m:
        raise RuntimeError("Custom latest episode not found")
    link = m.group(1)
    title = m.group(2).strip()
    if base_url:
        link = urljoin(base_url, link)
    return {"link": link, "title": title}

def extract_download_custom(html):
    """Custom extractor for download link."""
    # Example: find first <a> with href containing 'download' or specific host
    m = re.search(r'<a\s+href="([^"]*download[^"]*)"[^>]*>([^<]*)</a>', html, re.I)
    if not m:
        raise RuntimeError("Custom download link not found")
    link = m.group(1)
    host_text = m.group(2).strip()
    # Infer host from text or link
    host = "CustomHost"  # or parse from host_text
    return {"link": link, "host": host, "quality": "1080p"}