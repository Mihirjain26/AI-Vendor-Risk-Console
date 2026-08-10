from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests


# Standard headers to fetch a website
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
}

REQUEST_TIMEOUT = 10  # seconds — prevents a slow/unresponsive vendor site from hanging the pipeline
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:")


def fetch_website_contents(url):
    """
    Return the title and contents of the website at the given url;
    truncate to 2,000 characters as a sensible limit.
    Raises requests.HTTPError on non-2xx responses and
    requests.Timeout/ConnectionError on network failures, so callers
    can catch and report a clear reason instead of silently analyzing
    an error page.
    """
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.title.string if soup.title else "No title found"
    if soup.body:
        for irrelevant in soup.body(["script", "style", "img", "input"]):
            irrelevant.decompose()
        text = soup.body.get_text(separator="\n", strip=True)
    else:
        text = ""
    return (title + "\n\n" + text)[:2_000]


def fetch_website_links(url):
    """
    Return the links on the website at the given url, resolved to
    absolute https URLs, with mailto/tel/javascript links, bare
    anchors, and duplicates filtered out.

    I realize this is inefficient as we're parsing twice! This is to keep the code in the lab simple.
    Feel free to use a class and optimize it!
    """
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    raw_links = [link.get("href") for link in soup.find_all("a")]

    resolved = []
    seen = set()
    for href in raw_links:
        if not href:
            continue
        href = href.strip()
        if not href or href.startswith("#") or href.startswith(SKIP_SCHEMES):
            continue

        absolute = urljoin(url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue

        if absolute not in seen:
            seen.add(absolute)
            resolved.append(absolute)

    return resolved