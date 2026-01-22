"""
Custom extractors for anime grabber.

Define functions here for custom extraction logic.
Each function should match the signature expected by the grabber.

For extract_latest: def func(html, base_url=None) -> dict with "link" and "title"
For extract_download: def func(html) -> dict with "link", "host", "quality"
"""

import re
from urllib.parse import urljoin

DEFAULT_HOST_PRIORITY = ["Pdrain", "Mega", "Acefile", "GoFile", "KFiles", "ODFiles"]
DEFAULT_QUALITY = "1080p"

def extract_latest_default(html, base_url=None):
    """Default extractor for latest episode link and title using smokelister."""
    # Try smokelister -> first <ul> -> first <a>
    header_regex = re.compile(r'<div[^>]*class="smokelister"[^>]*>\s*<span[^>]*class="monktit"[^>]*>[^<]*episode list[^<]*', re.I)
    m = header_regex.search(html)
    if m:
        slice_html = html[m.start():]
        ul_match = re.search(r"<ul>([\s\S]*?)</ul>", slice_html, re.I)
        if ul_match:
            ul_content = ul_match.group(1)
            item = re.search(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', ul_content, re.I)
            if item:
                link = item.group(1)
                title = item.group(2).strip()
                if base_url:
                    link = urljoin(base_url, link)
                return {"link": link, "title": title}

    # Fallback: find first anchor that contains the word "Episode" or a number
    fallback = re.search(r'<a\s+href="([^"]+)"[^>]*>([^<]*episode[^<]*|[^<]*\d{1,3}[^<]*)</a>', html, re.I)
    if fallback:
        link = fallback.group(1)
        title = fallback.group(2).strip()
        if base_url:
            link = urljoin(base_url, link)
        return {"link": link, "title": title}

    raise RuntimeError("Latest episode block not found")

def extract_download_default(html):
    """Default extractor for download link using quality block."""
    quality = DEFAULT_QUALITY
    host_priority = DEFAULT_HOST_PRIORITY
    # Find marker for quality (e.g. <strong>Mp4 1080p</strong>)
    marker_regex = re.compile(r"<strong>\s*(?:mp4|mkv)\s*" + re.escape(quality) + r"\s*</strong>", re.I)
    m = marker_regex.search(html)
    if not m:
        raise RuntimeError(f"Section for quality {quality} not found")

    marker_start = m.start()
    # find nearest closing </li> after marker_start, else </ul>
    li_end = html.find("</li>", marker_start)
    ul_end = html.find("</ul>", marker_start)
    end_index = li_end if (li_end != -1 and (li_end < ul_end or ul_end == -1)) else ul_end
    if end_index == -1:
        # as last resort, take 1000 chars after marker
        block = html[marker_start: marker_start + 1000]
    else:
        block = html[marker_start:end_index]

    for host in host_priority:
        host_anchor = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>\s*' + re.escape(host) + r"\s*</a>", re.I)
        am = host_anchor.search(block)
        if am:
            return {"link": am.group(1), "host": host, "quality": quality}

    raise RuntimeError(f"No hosts from priority list found for quality {quality}")

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