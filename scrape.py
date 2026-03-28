#!/usr/bin/env python3
"""
Download justinluo.com (Framer SSR site) and all its assets locally.
Rewrites all asset URLs to point to local files.
"""

import os
import re
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL = "https://www.justinluo.com"
PAGES = [
    "/",
    "/projects",
    "/projects/prepared",
    "/projects/prepared-location",
    "/projects/prepared-analytics",
    "/projects/prepared-analytics-2",
    "/projects/prepared-voice",
    "/projects/teams-connect",
    "/projects/teams-edu",
    "/stack",
    "/contact",
    "/bookmarks",
    "/services",
]

OUTPUT_DIR = Path("/Users/justinluo/justinluo.com/site")
ASSETS_DIR = OUTPUT_DIR / "assets"

downloaded = {}  # url -> local path

def url_to_local_path(url):
    """Convert a URL to a local file path under ASSETS_DIR."""
    parsed = urllib.parse.urlparse(url)
    # Strip query params from path, keep them for uniqueness in filename
    path = parsed.path.lstrip("/")
    if parsed.query:
        # Encode query into filename
        safe_query = parsed.query.replace("=", "_").replace("&", "_").replace("-", "_")
        name, ext = os.path.splitext(path)
        path = f"{name}__{safe_query}{ext}"
    # Use domain as subfolder
    local = ASSETS_DIR / parsed.netloc / path
    return local

def download_asset(url):
    """Download an asset and return its local path. Returns None on failure."""
    # Normalize URL
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        return None
    # Strip fragment
    url = url.split("#")[0]
    if not url:
        return None

    # Skip same-site page URLs (not assets)
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc in ("www.justinluo.com", "justinluo.com"):
        return None

    if url in downloaded:
        return downloaded[url]

    local_path = url_to_local_path(url)
    if local_path.exists() and local_path.is_file():
        downloaded[url] = local_path
        return local_path

    # Ensure parent is a directory, not a file
    parent = local_path.parent
    if parent.exists() and not parent.is_dir():
        # Rename the conflicting file
        parent.rename(str(parent) + "_file")
    parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
        local_path.write_bytes(content)
        downloaded[url] = local_path
        print(f"  Downloaded: {url} -> {local_path.relative_to(OUTPUT_DIR)}")
        return local_path
    except Exception as e:
        print(f"  FAILED: {url} ({e})")
        downloaded[url] = None
        return None

def relative_path(from_file, to_file):
    """Get relative path from from_file to to_file."""
    return os.path.relpath(to_file, from_file.parent)

def rewrite_html(html_content, html_file):
    """Download all assets referenced in HTML and rewrite URLs."""

    def replace_url(url, attr=None):
        """Download url and return local relative path."""
        url = url.strip().strip("'\"")
        if not url or url.startswith("data:") or url.startswith("javascript:"):
            return url
        # Make absolute
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/") and not url.startswith("//"):
            url = BASE_URL + url
        elif not url.startswith("http"):
            return url

        local = download_asset(url)
        if local:
            return relative_path(html_file, local)
        return url

    # Rewrite src= attributes
    def rewrite_src(m):
        url = m.group(1)
        new_url = replace_url(url)
        return m.group(0).replace(url, new_url)

    # Rewrite href= for stylesheets and icons (not navigation links)
    def rewrite_href(m):
        full = m.group(0)
        url = m.group(1)
        # Skip internal page navigation links
        if url.startswith("/") and not any(url.endswith(ext) for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2", ".ttf"]):
            # Check if it's a framerusercontent or external asset link
            if "framerusercontent" not in full and "googletagmanager" not in full:
                return full
        new_url = replace_url(url)
        return full.replace(url, new_url)

    # src="..." and src='...'
    html_content = re.sub(r'src=["\']([^"\']+)["\']', rewrite_src, html_content)

    # href="..." for link tags (stylesheets, preload, etc.) - not <a> tags
    # We handle link[href] but not a[href]
    def rewrite_link_href(m):
        full = m.group(0)
        url = m.group(1)
        new_url = replace_url(url)
        return full.replace(url, new_url, 1)

    html_content = re.sub(
        r'(<link[^>]+href=["\'])([^"\']+)(["\'])',
        lambda m: m.group(1) + replace_url(m.group(2)) + m.group(3),
        html_content
    )

    # url(...) in inline styles
    def rewrite_css_url(m):
        url = m.group(1).strip("'\"")
        new_url = replace_url(url)
        return f"url({new_url})"

    html_content = re.sub(r'url\(([^)]+)\)', rewrite_css_url, html_content)

    # content="..." with image URLs in meta tags
    def rewrite_meta_content(m):
        full = m.group(0)
        url = m.group(1)
        if url.startswith("http"):
            new_url = replace_url(url)
            return full.replace(url, new_url, 1)
        return full

    html_content = re.sub(
        r'(<meta[^>]+content=["\'])([^"\']+)(["\'])',
        lambda m: m.group(1) + (replace_url(m.group(2)) if m.group(2).startswith("http") else m.group(2)) + m.group(3),
        html_content
    )

    # Also look for framerusercontent URLs in script content (JS strings)
    def rewrite_inline_framer_url(m):
        url = m.group(0)
        new_url = replace_url(url)
        return new_url

    html_content = re.sub(
        r'https://framerusercontent\.com/[^\s"\'<>)]+',
        rewrite_inline_framer_url,
        html_content
    )

    return html_content

def page_path_to_file(page_path):
    """Convert a URL path to an output HTML file path."""
    if page_path == "/":
        return OUTPUT_DIR / "index.html"
    clean = page_path.strip("/")
    return OUTPUT_DIR / clean / "index.html"

def fetch_page(url):
    """Fetch a page and return its HTML content."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for page_path in PAGES:
        url = BASE_URL + page_path
        out_file = page_path_to_file(page_path)
        print(f"\n{'='*60}")
        print(f"Fetching: {url}")

        try:
            html = fetch_page(url)
        except Exception as e:
            print(f"  ERROR fetching page: {e}")
            continue

        out_file.parent.mkdir(parents=True, exist_ok=True)
        print(f"  Processing assets...")
        html = rewrite_html(html, out_file)

        out_file.write_text(html, encoding="utf-8")
        print(f"  Saved: {out_file.relative_to(OUTPUT_DIR.parent)}")

    print(f"\n{'='*60}")
    print(f"Done! Site saved to: {OUTPUT_DIR}")
    print(f"Assets downloaded: {sum(1 for v in downloaded.values() if v)}")
    print(f"Assets failed: {sum(1 for v in downloaded.values() if not v)}")

if __name__ == "__main__":
    main()
